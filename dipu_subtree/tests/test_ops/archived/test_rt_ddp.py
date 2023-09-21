import os
import torch
import random
from torch import nn
import os
import sys
import tempfile
from torch._C import dtype
import torch
import torch.distributed as dist
import torch.nn as nn
import torch.optim as optim
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel as DDP

def setup(backend, rank, world_size, port):
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = str(port)
    print("comm using port:", str(port))
    # initialize the process group
    dist.init_process_group(backend=backend, rank=rank, world_size=world_size)

def cleanup():
    dist.destroy_process_group()

class ToyModel(nn.Module):
    def __init__(self):
        super(ToyModel, self).__init__()
        # self.net1 = nn.Linear(10, 10)
        # self.relu = nn.ReLU()
        self.net2 = nn.Linear(10, 5)

    def forward(self, x):
        # o1 = self.net1(x)
        # return self.net2(self.relu(o1))
        return self.net2(x)

def demo_basic_ddp(rank, world_size, port):
    import torch_dipu
    print(f"Running basic DDP example on rank {rank} {torch.cuda.current_device()}")
    torch.cuda.set_device(rank)
    backend  ="nccl"
    dev1 = rank

    # debugat(rank)
    setup(backend, rank, world_size, port)

    for i in range(1, 4):
        # create model and move it to GPU with id rank
        model = ToyModel().to(dev1)
        # ddp_model = DDP(model, device_ids=[dev1])
        ddp_model = DDP(model)

        loss_fn = nn.MSELoss()
        optimizer = optim.SGD(ddp_model.parameters(), lr=0.001, foreach=False)
        optimizer.zero_grad()

        in1 = torch.randn(20, 10).to(dev1)
        in1.requires_grad = True
        outputs = ddp_model(in1)
        outputs.backward(torch.ones_like(outputs))

        labels = torch.randn(20, 5).to(dev1)
        o1 = loss_fn(outputs, labels)
        o1.backward()
        optimizer.step()
        torch.cuda.synchronize()
        print("--------after bwd sync")
        assert model.net2.weight.grad is not None
    cleanup()

def demo_allreduce(rank, world_size, port):
    import torch_dipu
    print(f"Running basic DDP example on rank {rank} {torch.cuda.current_device()}")
    torch.cuda.set_device(rank)
    backend  ="nccl"
    dev1 = rank

    # debugat(rank)
    setup(backend, rank, world_size, port)

    world_size = dist.get_world_size()

    for op in [dist.reduce_op.SUM, dist.reduce_op.MAX, dist.reduce_op.MIN]:
        te_result = torch.zeros((3, 4)).to(dev1) + rank + 2
        dist.all_reduce(te_result, op=op)
    cleanup()

def demo_model_parallel(rank, world_size, port):
    print(f"Running DDP with model parallel example on rank {rank}.")
    backend  ="nccl"
    dev1 = rank

    # debugat(rank)
    setup(backend, rank, world_size)

    # setup mp_model and devices for this process
    dev0 = (rank * 2) % world_size
    dev1 = (rank * 2 + 1) % world_size
    mp_model = ToyMpModel(dev0, dev1)
    ddp_mp_model = DDP(mp_model)

    loss_fn = nn.MSELoss()
    optimizer = optim.SGD(ddp_mp_model.parameters(), lr=0.001)

    optimizer.zero_grad()
    # outputs will be on dev1
    outputs = ddp_mp_model(torch.randn(20, 10))
    labels = torch.randn(20, 5).to(dev1)
    loss_fn(outputs, labels).backward()
    optimizer.step()

    cleanup()

def run_demo(demo_fn, world_size, port):
    mp.spawn(demo_fn,
             args=(world_size, port,),
             nprocs=world_size,
             join=True)


if __name__ == "__main__":
    n_gpus = torch.cuda.device_count()
    # world_size = 1
    # demo_allreduce(0, world_size)
    # demo_basic_ddp(0, world_size)
    port = random.randint(10000, 60000)

    world_size = 1
    run_demo(demo_basic_ddp, world_size, port)
    run_demo(demo_allreduce, world_size, port)

    # run_demo(demo_model_parallel, world_size)