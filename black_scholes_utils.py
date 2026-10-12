
import numpy as np
import scipy.stats as ss
from scipy.stats import norm


## -- Black and Scholes
strike = 100
rate = 0.02
vol = 0.2
time = 1


def d1(S0, K, r, sigma, T):
    return (np.log(S0 / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))


def d2(S0, K, r, sigma, T):
    return (np.log(S0 / K) + (r - sigma**2 / 2) * T) / (sigma * np.sqrt(T))


def blackScholes(type, S0, K=strike, r=rate, sigma=vol, T=time):
    if type == "C":
        return S0 * ss.norm.cdf(d1(S0, K, r, sigma, T)) - K * np.exp(-r * T) * ss.norm.cdf(d2(S0, K, r, sigma, T))
    else:
        return K * np.exp(-r * T) * ss.norm.cdf(-d2(S0, K, r, sigma, T)) - S0 * ss.norm.cdf(-d1(S0, K, r, sigma, T))
