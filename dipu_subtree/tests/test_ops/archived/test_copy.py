# Copyright (c) 2023, DeepLink.
import torch
import torch_dipu
import itertools

def create_tensor(cfg):
    src_shape = cfg[0]
    dst_shape = cfg[1]
    src_need_expand = cfg[2]
    src_device = cfg[3]
    dst_device = cfg[4]
    src_dtype = cfg[5]
    dst_dtype = cfg[6]
    
    src_cpu = torch.randn(src_shape, dtype=src_dtype)
    dst_cpu = torch.randn(dst_shape, dtype=dst_dtype)
    src_dipu = src_cpu.to(src_device)
    dst_dipu = dst_cpu.to(dst_device)
    if src_need_expand:
        src_cpu = src_cpu.expand_as(dst_cpu)
        src_dipu = src_dipu.expand_as(dst_dipu)

    return src_cpu, dst_cpu, src_dipu, dst_dipu


def test_copy_():
    src_shapes = [(3, 2), (4, 3, 2)]
    dst_shapes = [(4, 3, 2)]
    src_need_expands = [True, False]
    devices = [torch.device("cpu"), torch.device("cuda:0")]
    dtypes = [torch.float32, torch.float16]
    
    configs = []
    for cfg in itertools.product(src_shapes, dst_shapes, src_need_expands, devices, devices, dtypes, dtypes):
        if cfg[3].type != 'cpu' or cfg[4].type != 'cpu':
            configs.append(cfg)
    
    for cfg in configs:
        print(f"cfg = {cfg}")
        src_cpu, dst_cpu, src_dipu, dst_dipu = create_tensor(cfg)
        dst_cpu.copy_(src_cpu)
        dst_dipu.copy_(src_dipu)
        if torch.allclose(dst_cpu, dst_dipu.cpu()):
            print(f"cfg = {cfg} passed")
        else:
            print(f"src_cpu = {src_cpu}")
            print(f"dst_cpu = {dst_cpu}")
            print(f"src_dipu = {src_dipu}")
            print(f"dst_dipu = {dst_dipu}")
            assert False, "copy_ test fail"


test_copy_()
