import torch 
from torch._jit_internal import weak_module, weak_script_method, List
from torch.nn.modules.utils import _pair
import torch.nn.functional as F
from torch.nn.parameter import Parameter
from math import sqrt
from ..device import device
from .common import QLayer
from ..functions import elastic_quant_connect
from ..utils.tools import flat_net




class LinearQuantLin(torch.nn.Module, QLayer):
    @staticmethod
    def convert(other, bottom=-1, top=1, size=5, alpha=0, beta=0):
        if not isinstance(other, torch.nn.Linear):
            raise TypeError("Expected a torch.nn.Linear ! Receive:  {}".format(other.__class__))
        result =  LinearQuantLin(other.in_features, other.out_features, False if other.bias is None else True, bottom=bottom, top=top, size=size, alpha=alpha, beta=beta)
        result.weight.data.copy_(other.weight.data)
        if not other.bias is None:
            result.bias.data.copy_(other.bias.data)
        return result

    def __init__(self, in_features, out_features, bias=True, bottom=-1, top=1, size=5, alpha=0, beta=0):
        torch.nn.Module.__init__(self)
        self.in_features = in_features
        self.out_features = out_features
        self.bottom = bottom
        self.top = top
        self.size = size
        self.register_buffer("alpha", torch.Tensor([alpha]))
        self.register_buffer("beta", torch.Tensor([beta]))

        self.weight = torch.nn.Parameter(torch.Tensor(out_features, in_features))
        if bias:
            self.bias = torch.nn.Parameter(torch.Tensor(out_features))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()
        self.linear_op = elastic_quant_connect.QuantLinDense(size=size, bottom=bottom, top=top)

    def reset_parameters(self):
        self.weight.data.uniform_(self.bottom, self.top)
        if self.bias is not None:
            self.bias.data.zero_()

    def clamp(self):
        self.weight.data.clamp_(self.bottom, self.top)
        if not self.bias is None:
            self.bias.data.clamp_(self.bottom, self.top) 

    def set_alpha(self, alpha):
        self.alpha = torch.Tensor([alpha]).to(self.weight.device)

    def set_beta(self, beta):
        self.beta = torch.Tensor([beta]).to(self.weight.device)

    def train(self, mode=True):
        self.training = mode
        #if self.training==mode:
        #    return
        #if mode:
        #    self.weight.data.copy_(self.weight.org.data)
        #else: # Eval mod
        #    if not hasattr(self.weight,'org'):
        #        self.weight.org=self.weight.data.clone()
        #    self.weight.org.data.copy_(self.weight.data)
        #    self.weight.data.copy_(elastic_quant_connect.lin_proj(self.weight, bottom=self.bottom, top=self.top, size=self.size).detach())

    def forward(self, input):
        if self.training :
            return self.linear_op.apply(input, self.weight, self.bias, self.alpha, self.beta)
        else:
            return torch.nn.functional.linear(input, elastic_quant_connect.lin_proj(self.weight, bottom=self.bottom, top=self.top, size=self.size), self.bias)


class LinearQuantLog(torch.nn.Module, QLayer):
    @staticmethod
    def convert(other, gamma=2, init=0.25, size=5, alpha=0, beta=0):
        if not isinstance(other, torch.nn.Linear):
            raise TypeError("Expected a torch.nn.Linear ! Receive:  {}".format(other.__class__))
        result = LinearQuantLog(other.in_features, other.out_features, False if other.bias is None else True, gamma=gamma, init=init, size=size, alpha=alpha, beta=beta)
        result.weight.data.copy_(other.weight.data)
        if not other.bias is None:
            result.bias.data.copy_(other.bias.data)
        return result

    def __init__(self, in_features, out_features, bias=True, gamma=2, init=0.25, size=5, alpha=0, beta=0):
        super(LinearQuantLog, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.gamma = gamma
        self.init = init
        self.size = size
        self.register_buffer("alpha", torch.Tensor([alpha]))
        self.register_buffer("beta", torch.Tensor([beta]))

        self.weight = torch.nn.Parameter(torch.Tensor(out_features, in_features))
        if bias:
            self.bias = torch.nn.Parameter(torch.Tensor(out_features))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()
        self.linear_op = elastic_quant_connect.QuantLogDense(gamma=gamma, init=init, size=size)
    
    def reset_parameters(self):
        self.weight.data.uniform_(-self.init*self.gamma**(self.size-1), self.init*self.gamma**(self.size-1))
        if self.bias is not None:
            self.bias.data.zero_()
    
    def train(self, mode=True):
        self.training = mode
        #if self.training==mode:
        #    return
        """
        if mode:
            self.weight.data.copy_(self.weight.org.data)
        else: # Eval mod
            if not hasattr(self.weight,'org'):
                self.weight.org=self.weight.data.clone()
            self.weight.org.data.copy_(self.weight.data)
            self.weight.data.copy_(elastic_quant_connect.exp_proj(self.weight, gamma=self.gamma, init=self.init, size=self.size).detach())
        """
    def clamp(self):
        self.weight.data.clamp_(-self.init*self.gamma**(self.size-1), self.init*self.gamma**(self.size-1))
        if not self.bias is None:
            self.bias.data.clamp_(-self.init*self.gamma**(self.size-1), self.init*self.gamma**(self.size-1))

    def set_alpha(self, alpha):
        self.alpha = torch.Tensor([alpha]).to(self.weight.device)

    def set_beta(self, beta):
        self.beta = torch.Tensor([beta]).to(self.weight.device)


    def forward(self, input):
        if self.training:
            return self.linear_op.apply(input, self.weight, self.bias, self.alpha, self.beta)
        else:
            return torch.nn.functional.linear(input, elastic_quant_connect.exp_proj(self.weight, init=self.init, gamma=self.gamma, size=self.size), self.bias)


class QuantConv2dLin(torch.nn.Conv2d, QLayer):

    @staticmethod
    def convert(other, bottom=-1, top=1, size=5, alpha=0, beta=0):
        if not isinstance(other, torch.nn.Conv2d):
            raise TypeError("Expected a torch.nn.Conv2d ! Receive:  {}".format(other.__class__))
        result= QuantConv2dLin(other.in_channels, other.out_channels, other.kernel_size, stride=other.stride,
                         padding=other.padding, dilation=other.dilation, groups=other.groups,
                         bias=False if other.bias is None else True, bottom=bottom, top=top, size=size, alpha=alpha, beta=beta)
        result.weight.data.copy_(other.weight.data)
        if not other.bias is None:
            result.bias.data.copy_(other.bias.data)
        return result

    def __init__(self, in_channels, out_channels, kernel_size,  bottom=-1, top=1, size=5, alpha=0, beta=0,  stride=1, padding=1, dilation=1, groups=1, bias=True):
        self.top = top
        self.bottom = bottom
        self.size = size
        torch.nn.Conv2d.__init__(self, in_channels, out_channels, kernel_size,  stride=stride, padding=padding, dilation=dilation, groups=groups, bias=bias)
        self.register_buffer("alpha", torch.Tensor([alpha]))
        self.register_buffer("beta", torch.Tensor([beta]))

        self.weight_op = elastic_quant_connect.QuantWeightLin(self.top, self.bottom, self.size)


    def train(self, mode=True):
        self.training = mode
        #if self.training==mode:
        #    return
        #if mode:
        #    self.weight.data.copy_(self.weight.org.data)
        #else: # Eval mod
        #    if not hasattr(self.weight,'org'):
        #        self.weight.org=self.weight.data.clone()
        #    self.weight.org.data.copy_(self.weight.data)
        #    self.weight.data.copy_(elastic_quant_connect.lin_proj(self.weight, bottom=self.bottom, top=self.top, size=self.size).detach())

    """
    def reset_parameters(self):
        self.weight.data.uniform_(self.bottom, self.top)
        if self.bias is not None:
            self.bias.data.zero_()
    """
    def clamp(self):
        self.weight.data.clamp_(self.bottom, self.top)
        if not self.bias is None:
            self.bias.data.clamp_(self.bottom, self.top) 

    def set_alpha(self, alpha):
        self.alpha = torch.Tensor([alpha]).to(self.weight.device)

    def set_beta(self, beta):
        self.beta = torch.Tensor([beta]).to(self.weight.device)

    def forward(self, input):
        if self.training:
            out = torch.nn.functional.conv2d(input, self.weight_op.apply(self.weight, self.alpha, self.beta), self.bias, self.stride, self.padding, self.dilation, self.groups)
        else:
            out = torch.nn.functional.conv2d(input, elastic_quant_connect.lin_proj(self.weight, bottom=self.bottom, top=self.top, size=self.size), self.bias, self.stride, self.padding, self.dilation, self.groups)

        return out

class QuantConv2dLog(torch.nn.Conv2d, QLayer):

    @staticmethod
    def convert(other, gamma=2, init=0.25, size=5, alpha=0, beta=0):
        if not isinstance(other, torch.nn.Conv2d):
            raise TypeError("Expected a torch.nn.Conv2d ! Receive:  {}".format(other.__class__))
        result =  QuantConv2dLog(other.in_channels, other.out_channels, other.kernel_size, stride=other.stride,
                         padding=other.padding, dilation=other.dilation, groups=other.groups,
                         bias=False if other.bias is None else True,  gamma=gamma, init=init, size=size, alpha=alpha, beta=beta)
        
        result.weight.data.copy_(other.weight.data)
        if not other.bias is None:
            result.bias.data.copy_(other.bias.data)
        return result

    def __init__(self, in_channels, out_channels, kernel_size,  gamma=2, init=0.25, size=5, alpha=0, beta=0,  stride=1, padding=1, dilation=1, groups=1, bias=True):
        torch.nn.Conv2d.__init__(self, in_channels, out_channels, kernel_size,  stride=stride, padding=padding, dilation=dilation, groups=groups, bias=bias)
        self.gamma = gamma
        self.init = init
        self.size = size
        self.register_buffer("alpha", torch.Tensor([alpha]))
        self.register_buffer("beta", torch.Tensor([beta]))
        self.weight_op = elastic_quant_connect.QuantWeightExp(gamma=self.gamma, init=self.init, size=self.size)


    def train(self, mode=True):
        self.training = mode
        #if self.training==mode:
        #    return
        #if mode:
        #    self.weight.data.copy_(self.weight.org.data)
        #else: # Eval mod
        #    if not hasattr(self.weight,'org'):
        #        self.weight.org=self.weight.data.clone()
        #    self.weight.org.data.copy_(self.weight.data)
        #    self.weight.data.copy_(elastic_quant_connect.lin_proj(self.weight, bottom=self.bottom, top=self.top, size=self.size).detach())

    """
    def reset_parameters(self):
        self.weight.data.uniform_(self.bottom, self.top)
        if self.bias is not None:
            self.bias.data.zero_()
    """
    def clamp(self):
        self.weight.data.clamp_(self.bottom, self.top)
        if not self.bias is None:
            self.bias.data.clamp_(self.bottom, self.top) 

    def set_alpha(self, alpha):
        self.alpha = torch.Tensor([alpha]).to(self.weight.device)

    def set_beta(self, beta):
        self.alpha = torch.Tensor([beta]).to(self.weight.device)

    def forward(self, input):
        if self.training:
            out = torch.nn.functional.conv2d(input, self.weight_op.apply(self.weight, self.alpha, self.beta), self.bias, self.stride, self.padding, self.dilation, self.groups)
        else:
            out = torch.nn.functional.conv2d(input, elastic_quant_connect.exp_proj(self.weight, init=self.init, gamma=self.gamma, size=self.size), self.bias, self.stride, self.padding, self.dilation, self.groups)

        return out



def set_model_alpha(model, alpha):
    layers  = flat_net(model, (LinearQuantLin, LinearQuantLog, QuantConv2dLin, QuantConv2dLog))
    for layer in layers:
        layer.set_alpha(alpha)

def set_model_beta(model, beta):
    layers  = flat_net(model,  (LinearQuantLin, LinearQuantLog, QuantConv2dLin, QuantConv2dLog))
    for layer in layers:
        layer.set_beta(beta)
