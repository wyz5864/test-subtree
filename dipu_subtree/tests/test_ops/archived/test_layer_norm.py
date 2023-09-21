# Copyright (c) 2023, DeepLink.
import torch
import numpy as np

from torch_dipu.testing._internal.common_utils import create_common_tensor, TestCase, run_tests


class TestLayerNorm(TestCase):

    def init_module(self, normalized_shape, elementwise_affine = False):
        self.normalized_shape = normalized_shape
        self.cpu_module = torch.nn.LayerNorm(self.normalized_shape, elementwise_affine = elementwise_affine)
        self.dipu_module = torch.nn.LayerNorm(self.normalized_shape, elementwise_affine = elementwise_affine)
        self.dipu_module = self.dipu_module.cuda()

    def run_layer_norm(self):
        x1 = self.x.clone().cpu()
        x1.requires_grad = True
        y1 = self.cpu_module(x1)
        y1.backward(torch.ones_like(y1))

        x2 = self.x.clone().cuda()
        x2.requires_grad = True
        print(self.dipu_module, self.dipu_module.weight is None)
        y2 = self.dipu_module(x2)
        y2.backward(torch.ones_like(y2))

        self.assertTrue(torch.allclose(y1, y2.cpu(), atol=1e-3, rtol=1e-4))
        print('forward ok')
        self.assertTrue(torch.allclose(x1.grad, x2.grad.cpu(), atol=1e-3, rtol=1e-4))
        print('input.grad ok')
        if self.cpu_module.elementwise_affine == True and self.cpu_module.weight.grad is not None:
            self.assertTrue(torch.allclose(self.cpu_module.weight.grad, self.dipu_module.weight.grad.cpu(), atol=1e-3, rtol=1e-4))
            self.assertTrue(torch.allclose(self.cpu_module.bias.grad, self.dipu_module.bias.grad.cpu(), atol=1e-3, rtol=1e-4))
            print('param.grad ok')

    def test_layer_norm_affine(self):
        normalized_shape = [3, 4, 5, 6, 7, 8]
        self.init_module(normalized_shape, elementwise_affine = True)
        self.x = torch.randn([4,] + normalized_shape)
        self.run_layer_norm()

    def test_layer_norm_no_affine(self):
        normalized_shape = [3, 4, 5, 6, 7]
        self.init_module(normalized_shape, elementwise_affine = False)
        self.x = torch.randn([4,] + normalized_shape)
        self.run_layer_norm()


if __name__ == "__main__":
    run_tests()
