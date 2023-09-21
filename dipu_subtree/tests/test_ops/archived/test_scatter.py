import torch
import torch_dipu

src = torch.arange(1, 11).reshape((2, 5))
index = torch.tensor([[0, 1, 2, 0]])
y1 = torch.zeros(3, 5, dtype=src.dtype).scatter_(0, index, src)
y2 = torch.zeros(3, 5, dtype=src.dtype).cuda().scatter_(0, index.cuda(), src.cuda())
assert torch.allclose(y1, y2.cpu())

#The reduction operation of multiply is not supported by camb
y1 = torch.zeros(3, 5, dtype=src.dtype).scatter_(0, index, src, reduce='add')
y2 = torch.zeros(3, 5, dtype=src.dtype).cuda().scatter_(0, index.cuda(), src.cuda(), reduce='add')
assert torch.allclose(y1, y2.cpu())

y1 = torch.full((2, 4), 2.).scatter_(1, torch.tensor([[2], [3]]), 1.23)
y2 = torch.full((2, 4), 2.).cuda().scatter_(1, torch.tensor([[2], [3]]).cuda(), 1.23)
assert torch.allclose(y1, y2.cpu())

y1 = torch.full((2, 4), 2.).scatter_(1, torch.tensor([[2], [3]]), 1.23, reduce='add')
y2 = torch.full((2, 4), 2.).cuda().scatter_(1, torch.tensor([[2], [3]]).cuda(), 1.23, reduce='add')
assert torch.allclose(y1, y2.cpu())

# for testing aten::scatter_add.out
y1 = torch.full((3, 5), 2).scatter_add(0, index, src)
y2 = torch.full((3, 5), 2).cuda().scatter_add(0, index.cuda(), src.cuda())
assert torch.allclose(y1, y2.cpu())