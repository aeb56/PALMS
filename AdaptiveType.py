from __future__ import annotations

import math
from typing import Type

from Environment import Stimulus

class AdaptiveType:
    betan: float
    betap: float
    lamda: float
    xi_hall: None | float
    gamma: float
    thetaE: float
    thetaI: float

    def __init__(self, betan: float, betap: float, lamda: float, xi_hall: None | float, gamma: float, thetaE: float, thetaI: float):
        self.betan = betan
        self.betap = betap
        self.lamda = lamda
        self.xi_hall = xi_hall
        self.gamma = gamma
        self.thetaE = thetaE
        self.thetaI = thetaI

    @classmethod
    def types(cls) -> dict[str, Type[AdaptiveType]]:
        return {
            'Rescorla Wagner': RescorlaWagner,
            'Rescorla Wagner Linear': RescorlaWagnerLinear,
            'Pearce Kaye Hall': PearceKayeHall,
            'LePelley': LePelley,
            'LePelley Hybrid': LePelleyHybrid,
            'PALMS Hybrid': Hybrid,
            'PALMS HybridFix': HybridFix,
             'MLAB Hybrid': MlabHybrid,
            
        }

    @classmethod
    def get(cls, adaptive_type_name, *args, **kwargs) -> AdaptiveType:
        return cls.types()[adaptive_type_name](*args, **kwargs)

    @classmethod
    def parameters(cls) -> list[str]:
        return [
            'alpha',
            'alpha_mack',
            'alpha_hall',
            'beta',
            'betan',
            'lamda',
            'gamma',
            'thetaE',
            'thetaI',
            'salience',
            'habituation',
            'rho',
            'nu',
        ]

    @classmethod
    def should_plot_macknhall(cls) -> bool:
        return 'alpha_mack' in cls.parameters() and 'alpha_hall' in cls.parameters()

    @classmethod
    def first_defaults(cls) -> dict[str, float]:
        return dict(
            alpha = 0.1,
            alpha_mack = 0.1,
            alpha_hall = 0.1,
            salience = 0.5,
            lamda = 1,
            beta = 0.3,
            betan = 0.2,
            gamma = 0.5,
            thetaE = 0.3,
            thetaI = 0.1,
            habituation = 0.99,
            rho = 0.2,
            nu=0.25,
            window_size = 10,
            num_trials = 100,
        )

    @classmethod
    def defaults(cls) -> dict[str, float]:
        return {}

    def get_alpha_mack(self, s: Stimulus, sigma: float) -> float:
        return 1/2 * (1 + 2*s.assoc - sigma)

    def get_alpha_hall(self, s: Stimulus, sigma: float, lamda: float) -> float:
        assert self.xi_hall is not None

        delta_ma_hall = s.delta_ma_hall or 0

        surprise = abs(lamda - sigma)
        window_term =  1 - self.xi_hall * math.exp(-delta_ma_hall**2 / 2)
        gamma = 0.99
        kayes = gamma*surprise +  (1-gamma)*s.alpha_hall

        new_error = kayes

        return new_error

    def run_step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float, count: float):
        self.delta_v_factor = beta * (lamda - sigma)
        try:
            self.step(s = s, beta = beta, lamda = lamda, sign = sign, sigma = sigma, sigmaE = sigmaE, sigmaI = sigmaI, count =  count)
        except OverflowError:
            print(f'{lamda=}\t{sigma=}')
            raise

    def step(self, *, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        raise NotImplementedError('Calling step in abstract function is undefined.')

class RescorlaWagner(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, *, s: Stimulus, **kwargs):
        s.assoc += s.alpha * self.delta_v_factor

class RescorlaWagnerLinear(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, *, s: Stimulus,sign: int, **kwargs):
        s.alpha *= 1 + sign * 0.05
        s.alpha = min(max(s.alpha, 0.05), 1)
        s.assoc += s.alpha * self.delta_v_factor

class PearceHall(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'lamda', 'sigma', 'salience']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        s.alpha = abs(lamda - sigma)
        s.assoc += s.salience * s.alpha * abs(lamda)

class PearceKayeHall(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda', 'gamma']

    def step(self, *, s: Stimulus, lamda: float, sigmaE: float, sigmaI: float, **kwargs):
        rho = lamda - (sigmaE - sigmaI)

        if rho >= 0:
            s.Ve += self.betap * s.alpha * lamda
        else:
            s.Vi += self.betan * s.alpha * abs(rho)

        s.alpha = self.gamma * abs(rho) + (1 - self.gamma) * s.alpha
        s.assoc = s.Ve - s.Vi

class LePelley(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda', 'thetaE', 'thetaI']

    def step(self, *, s: Stimulus, lamda: float, sigmaE: float, sigmaI: float, **kwargs):
        rho = lamda - (sigmaE - sigmaI)

        VXe = sigmaE - s.Ve
        VXi = sigmaI - s.Vi

        DVe = 0.
        DVi = 0.
        if rho >= 0:
            DVe = s.alpha * self.betap * (1 - s.Ve + s.Vi) * abs(rho)

            if rho > 0:
                s.alpha += -self.thetaE * (abs(lamda - s.Ve + s.Vi) - abs(lamda - VXe + VXi))
        else:
            DVi = s.alpha * self.betan * (1 - s.Vi + s.Ve) * abs(rho)
            s.alpha += -self.thetaI * (abs(abs(rho) - s.Vi + s.Ve) - abs(abs(rho) - VXi + VXe))

        s.alpha = min(max(s.alpha, 0.05), 1)
        s.Ve += DVe
        s.Vi += DVi

        s.assoc = s.Ve - s.Vi

class LePelleyHybrid(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha_mack', 'alpha_hall', 'beta', 'betan', 'lamda', 'gamma', 'thetaE', 'thetaI']

    @classmethod
    def defaults(cls) -> dict[str, float]:
        return dict(
            alpha_mack = .9,
            alpha_hall = .9,
        )

    def step(self, *, s: Stimulus, lamda: float, sigmaE: float, sigmaI: float, **kwargs):
        rho = lamda - (sigmaE - sigmaI)

        VXe = sigmaE - s.Ve
        VXi = sigmaI - s.Vi

        DVe = 0.
        DVi = 0.
        if rho >= 0:
            DVe = s.alpha_mack * self.betap * s.alpha_hall * (1 - s.Ve + s.Vi) * abs(rho)

            if rho > 0:
                s.alpha_mack += -self.thetaE * s.alpha_hall * (abs(lamda - s.Ve + s.Vi) - abs(lamda - VXe + VXi))
        else:
            DVi = s.alpha_mack * self.betan * s.alpha_hall * (1 - s.Vi + s.Ve) * abs(rho)
            s.alpha_mack += -self.thetaI * (abs(abs(rho) - s.Vi + s.Ve) - abs(abs(rho) - VXi + VXe))

        s.alpha_hall = self.gamma * abs(rho) + (1 - self.gamma) * s.alpha_hall
        s.alpha_mack = min(max(s.alpha_mack, 0.05), 1)
        s.alpha_hall = min(max(s.alpha_hall, 0.5), 1)

        s.Ve += DVe
        s.Vi += DVi
        s.assoc = s.Ve - s.Vi

class RescorlaWagnerExponential(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        if sign == 1:
            s.alpha *= (s.alpha ** 0.05) ** sign
        s.assoc += s.alpha * self.delta_v_factor

class Mack(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        s.alpha_mack = self.get_alpha_mack(s, sigma)
        s.alpha = s.alpha_mack
        s.assoc = s.assoc * self.delta_v_factor + self.delta_v_factor/2*beta

class Hall(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        s.alpha_hall = self.get_alpha_hall(s, sigma, lamda)
        s.alpha = s.alpha_hall
        self.delta_v_factor = 0.5 * abs(lamda)
        s.assoc += s.alpha * beta * (lamda - sigma)

class Macknhall(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        s.alpha_mack = self.get_alpha_mack(s, sigma)
        s.alpha_hall = self.get_alpha_hall(s, sigma, lamda)
        s.alpha = (1 - abs(lamda - sigma)) * s.alpha_mack + s.alpha_hall
        s.assoc += s.alpha * self.delta_v_factor

class NewDualV(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        rho = lamda - (sigmaE - sigmaI)

        delta_ma_hall = s.delta_ma_hall or 0
        self.gamma = 1 - math.exp(-delta_ma_hall**2)

        if rho >= 0:
            s.Ve += self.betap * s.alpha * lamda
        else:
            s.Vi += self.betan * s.alpha * abs(rho)

        s.alpha = self.gamma * abs(rho) + (1 - self.gamma) * s.alpha
        s.assoc = s.Ve - s.Vi

class Dualmack(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        rho = lamda - (sigmaE - sigmaI)

        VXe = sigmaE - s.Ve
        VXi = sigmaI - s.Vi

        if rho >= 0:
            s.Ve += s.alpha * self.betap * (1 - s.Ve + s.Vi) * abs(rho)
        else:
            s.Vi += s.alpha * self.betan * (1 - s.Vi + s.Ve) * abs(rho)

        s.alpha = 1/2 * (1 + s.assoc - (VXe - VXi))
        s.assoc = s.Ve - s.Vi

class OldHybrid(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha', 'beta', 'betan', 'lamda', 'alpha_mack', 'alpha_hall', 'thetaE', 'thetaI', 'gamma']

    def step(self, s: Stimulus, beta: float, lamda: float, sign: int, sigma: float, sigmaE: float, sigmaI: float):
        rho = lamda - (sigmaE - sigmaI)

        NVe = 0.
        NVi = 0.
        if rho >= 0:
            DVe = s.alpha_hall * self.betap * (1 - s.Ve + s.Vi) * abs(rho)
            NVe = s.Ve + DVe
            NVi = s.Vi
        else:
            NVe = s.Ve
            DvI = s.alpha_hall * self.betan * (1 - s.Vi + s.Ve) * abs(rho)
            NVi = s.Vi + DvI

        VXe = sigmaE - s.Ve
        VXi = sigmaI - s.Vi
        if rho > 0:
            s.alpha_mack += -self.thetaE * (abs(lamda - s.Ve + s.Vi) - abs(lamda - VXe + VXi))
        elif rho < 0:
            s.alpha_mack += -self.thetaI * (abs(abs(rho) - s.Vi + s.Ve) - abs(abs(rho) - VXi + VXe))

        s.alpha_mack = min(max(s.alpha_mack, 0.05), 1)
        s.alpha_hall = self.gamma * abs(rho) + (1 - self.gamma) * s.alpha_hall

        s.Ve = NVe
        s.Vi = NVi

        s.assoc = s.alpha_mack * (s.Ve - s.Vi)

class Hybrid(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha_mack', 'alpha_hall', 'salience', 'habituation', 'lamda']

    @classmethod
    def defaults(cls) -> dict[str, float]:
        return dict(
            salience = .5,
            habituation = 0.99,
            alpha_mack = 0.1,
            alpha_hall = 0.3,
            lamda = 1,
        )

    def step(self, *, s: Stimulus, lamda: float, sigma: float, **kwargs):
        s.habituation = s.habituation_0 - s.salience_0 * (1 - s.habituation)
        s.alpha_hall = (1 - s.habituation) * (lamda - sigma) ** 2 + s.habituation * s.alpha_hall
        s.alpha_mack = ((1 - s.alpha_mack) * (2 * s.assoc - sigma)) ** 2 + (1 - (s.alpha_hall_0 + (1 - s.salience_0) * (1 - s.alpha_hall_0))) ** 2

        DV = s.alpha_hall * (lamda - sigma)
        s.assoc = s.assoc + DV * s.alpha_mack

class HybridFix(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha_mack', 'alpha_hall', 'salience', 'habituation', 'lamda']

    @classmethod
    def defaults(cls) -> dict[str, float]:
        return dict(
            salience = .5,
            habituation = 0.99,
            alpha_mack = 0.1,
            alpha_hall = 0.3,
            lamda = 1,
        )

    def step(self, *, s: Stimulus, lamda: float, sigma: float, **kwargs):
        s.habituation = s.habituation_0 - s.salience_0 * (1 - s.habituation)
        s.alpha_hall = (1 - s.habituation) * (lamda - sigma) ** 2 + s.habituation * s.alpha_hall
        s.alpha_mack = ((1 - s.alpha_mack) * (2 * s.assoc - sigma)) ** 2 + (1 - (s.alpha_hall_0 + (1 - s.salience_0) * (1 - s.alpha_hall_0))) ** 2

        DV = s.alpha_hall * (lamda - sigma)
        s.assoc = s.assoc * s.alpha_mack + DV 

class MlabHybrid(AdaptiveType):
    @classmethod
    def parameters(cls) -> list[str]:
        return ['alpha','salience', 'habituation', 'lamda','rho','nu']

    @classmethod
    def defaults(cls) -> dict[str, float]:
        return dict(
            salience = .5,
            habituation = 0.99,
            alpha_mack = 0.1,
            alpha_hall = 0.3,
            lamda = 1,
            rho = 0.2,
            nu = 0.25,
        )

    def step(self, *, s: Stimulus, lamda: float, sigma: float, count: float, **kwargs):
        s.habituation = s.habituation_0 - s.salience_0 * (1 - s.habituation)
        self.alpha = (s.habituation/count) * (s.nu*(lambda-sigma)**2 + s.rho*(s.assoc-max()))

        DV = s.alpha_hall * (lamda - sigma)
        s.assoc = s.assoc * s.alpha_mack + DV 
