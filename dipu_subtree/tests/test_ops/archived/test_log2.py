# Copyright (c) 2023, DeepLink.
import torch
import torch_dipu

device = torch.device("dipu")
input = torch.tensor([1.0, 2.0, 3.0]).to(device)
y = torch.log2(input)
print(y)

input.log2_()
print(input)