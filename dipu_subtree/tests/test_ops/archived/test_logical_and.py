import torch
import torch_dipu

torch.logical_and(torch.tensor([True, False, True]), torch.tensor([True, False, False]))
a = torch.tensor([0, 1, 10, 0], dtype=torch.int8)
b = torch.tensor([4, 0, 1, 0], dtype=torch.int8)
assert torch.allclose(torch.logical_and(a.cuda(), b.cuda()).cpu(), torch.logical_and(a, b))
assert torch.allclose(torch.logical_and(a.double().cuda(), b.double().cuda()).cpu(), torch.logical_and(a.double(), b.double()))
assert torch.allclose(torch.logical_and(a.double().cuda(), b.cuda()).cpu(), torch.logical_and(a.double(), b))
assert torch.allclose(torch.logical_and(a.cuda(), b.cuda(), out=torch.empty(4, dtype=torch.bool).cuda()).cpu(), torch.logical_and(a, b, out=torch.empty(4, dtype=torch.bool)))