import torch
import torch_dipu

x = torch.tensor([0.1, 1.2, -0.8, 0.3, 0.7]).cuda()
y = torch.tensor([0.1, 1.2, -0.8, 0.3, 0.7])

x.clamp_min_(0.0)
y.clamp_min_(0.0)
assert torch.allclose(x.cpu(), y, atol = 1e-3, rtol = 1e-3)

x.clamp_max_(0.5)
y.clamp_max_(0.5)
assert torch.allclose(x.cpu(), y, atol = 1e-3, rtol = 1e-3)

min = torch.tensor([0.2])
x.clamp_min_(min.cuda())
y.clamp_min_(min)
assert torch.allclose(x.cpu(), y, atol = 1e-3, rtol = 1e-3)

min2 = torch.tensor([0.4])
torch.clamp_min(x, min2.cuda())
torch.clamp_min(y, min2)
assert torch.allclose(x.cpu(), y, atol = 1e-3, rtol = 1e-3)