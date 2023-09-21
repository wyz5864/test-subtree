# Copyright (c) 2023, DeepLink.
import torch
import torch.nn.functional as F
import torch_dipu

def test_nll_loss(input, target, devicestr : str):
    device = torch.device(devicestr)
    input = input.to(device)
    input.requires_grad_(True)
    target = target.to(device)
    loss = F.nll_loss(F.log_softmax(input, dim=1), target)
    print(f"loss = {loss}")

    loss.backward()
    print(f"input.grad = {input.grad}")


input = torch.randn(3, 5)
target = torch.tensor([1, 0, 4])
test_nll_loss(input, target, "dipu")
test_nll_loss(input, target, "cpu")