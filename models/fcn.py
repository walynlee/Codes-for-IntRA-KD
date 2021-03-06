from torch import nn
from . import fc_resnet


class FCN(nn.Module):
    def __init__(self, num_class, base_model='resnet50', dropout=0.1, partial_bn=True):
        super(FCN, self).__init__()

        self._enable_pbn = partial_bn
        self.num_class = num_class

        if partial_bn:
            self.partialBN(True)
        self._prepare_base_model(base_model)
        self.classifier = nn.Sequential(
            nn.Conv2d(self.base_model.feature_dim, 512, kernel_size=3, padding=1, bias=False),
            nn.ReLU(inplace=True),
            nn.Dropout2d(p=dropout),
            nn.Conv2d(512, num_class, kernel_size=1), )

    def _prepare_base_model(self, base_model):
        if 'resnet' in base_model:
            self.base_model = getattr(fc_resnet, 'fc_' + base_model)(pretrained=True)
            self.input_mean = [0.485 * 255, 0.456 * 255, 0.406 * 255] # self.base_model.input_mean
            self.input_std = [0.229 * 255, 0.224 * 255, 0.225 * 255] # self.base_model.input_std
        else:
            raise ValueError('Unknown base model: {}'.format(base_model))

    def train(self, mode=True):
        """
        Override the default train() to freeze the BN parameters
        :return:
        """
        super(FCN, self).train(mode)
        if self._enable_pbn:
            print("Freezing BatchNorm2D.")
            for m in self.base_model.modules():
                if isinstance(m, nn.BatchNorm2d):
                    m.eval()
                    m.weight.requires_grad = False
                    m.bias.requires_grad = False

    def partialBN(self, enable):
        self._enable_pbn = enable

    def get_optim_policies(self):
        base_weight = []
        base_bias = []
        base_bn = []

        addtional_weight = []
        addtional_bias = []
        addtional_bn = []

        for m in self.base_model.modules():
            if isinstance(m, nn.Conv2d):
                ps = list(m.parameters())
                base_weight.append(ps[0])
                if len(ps) == 2:
                    base_bias.append(ps[1])
            elif isinstance(m, nn.BatchNorm2d):
                base_bn.extend(list(m.parameters()))

        if self.classifier is not None:
            for m in self.classifier.modules():
                if isinstance(m, nn.Conv2d):
                    ps = list(m.parameters())
                    addtional_weight.append(ps[0])
                    if len(ps) == 2:
                        addtional_bias.append(ps[1])
                elif isinstance(m, nn.BatchNorm2d):
                    addtional_bn.extend(list(m.parameters()))

        return [
            {
                'params': addtional_weight,
                'lr_mult': 10,
                'decay_mult': 1,
                'name': "addtional weight"
            },
            {
                'params': addtional_bias,
                'lr_mult': 20,
                'decay_mult': 0,
                'name': "addtional bias"
            },
            {
                'params': addtional_bn,
                'lr_mult': 10,
                'decay_mult': 1,
                'name': "addtional BN scale/shift"
            },
            {
                'params': base_weight,
                'lr_mult': 1,
                'decay_mult': 1,
                'name': "base weight"
            },
            {
                'params': base_bias,
                'lr_mult': 2,
                'decay_mult': 0,
                'name': "base bias"
            },
            {
                'params': base_bn,
                'lr_mult': 1,
                'decay_mult': 1,
                'name': "base BN scale/shift"
            },
        ]

    def forward(self, x):

        input_size = tuple(x.size()[2:4])
        x = self.base_model(x)
        x = self.classifier(x)
        x = nn.functional.upsample(x, size=input_size, mode='bilinear')

        return x
