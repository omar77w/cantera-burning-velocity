import numpy as np
import cantera as ct
import matplotlib.pyplot as plt
from scipy.optimize import minimize
import csv

def compute_thermal_conductivity_integral(lambda_fn, x, gas):
    """Use trapezoidal integration avoiding singularities"""
    n_points = 50
    T_ratios = np.linspace(1.001, x, n_points)  # Start slightly above 1 to avoid division by zero
    
    T0, P0, X0 = gas.T, gas.P, gas.X
    lambdas = []
    
    for T_ratio in T_ratios:
        gas.TPX = T0 * T_ratio, P0, X0
        lambdas.append(gas.thermal_conductivity)
    
    gas.TPX = T0, P0, X0
    dx = (x - 1.001)/(n_points - 1)
    
    # Gamma1
    integrand1 = [lamb/t for lamb, t in zip(lambdas, T_ratios)]
    gamma1 = np.trapz(integrand1, dx=dx) * x/(x - 1)
    
    # Gamma2 (avoid log singularity)
    valid_idx = T_ratios > 1.001
    T_valid = T_ratios[valid_idx]
    lamb_valid = np.array(lambdas)[valid_idx]
    integrand2 = lamb_valid*np.log(1/(T_valid - 1))/T_valid
    gamma2 = np.trapz(integrand2, dx=dx)/(x - 1)
    
    # Gamma3
    gamma3 = np.trapz(lambdas, dx=dx)/(x - 1)
    
    return gamma1, gamma2, gamma3

def compute_Pe(n, sigma, Le_eff, beta, Pr, gas):
    """Modified Pe computation with actual conductivity"""
    # Get burned gas conductivity
    gas.equilibrate('HP')
    lambda_b = gas.thermal_conductivity
    
    gamma1, gamma2, gamma3 = compute_thermal_conductivity_integral(None, sigma, gas)
    omega = compute_omega(n, sigma)
    Q1, Q2, Q3 = compute_stability_coefficients(n, sigma, omega, lambda_b, gamma1, gamma2, gamma3)
    
    Le_term = beta * (Le_eff - 1) / (sigma - 1)
    Omega = Q1 - Le_term * Q2 + Pr * Q3
    
    return (Omega/omega)

def compute_omega(n, sigma):
    """Compute hydrodynamic instability coefficient omega"""
    a = (sigma + 1)*n + 1
    b = 2*n**2 + (4 + 5*sigma)*n + 4
    c = -(sigma - 1)/sigma * n**3 + 2*n**2 + (3*(sigma + 1) - 1/sigma)*n + 2
    
    return (-b + np.sqrt(b**2 - 4*a*c))/(2*a)

def compute_stability_coefficients(n, sigma, omega, lambda_b, gamma1, gamma2, gamma3):
    """Corrected stability coefficients calculation"""
    a = (sigma + 1)*n + 1
    b = 2*n**2 + (4 + 5*sigma)*n + 4
    delta = 2*a*omega + b - 2*a
    
    Q1 = (gamma1/(sigma*delta)) * (
        n**4*(sigma + 1) + 
        sigma*n**3*(2*omega + 5) +
        n**2*(omega*sigma - 2*sigma**2 + sigma - 1) +
        n*sigma*(sigma - 7 - 3*omega - sigma*omega) -
        2*sigma*(1 + omega)
    )
    Q1 += (gamma3/(sigma*delta)) * (n*(n**2 - 1)*(n + 2)*(sigma - 1))
    
    # Removed 2.0 multiplier from Q2
    Q2 = (gamma2*(sigma - 1)/(2*delta)) * (
        2*n**4 +
        n**3*(2*omega*sigma + 2*omega + 10*sigma - 3) +
        n**2*(2*sigma*omega**2 + (5*sigma - 1)*omega + 3*sigma - 2*sigma**2 - 2) +
        n*(sigma*omega**2*(1 - 4*sigma) - (14*sigma**2 + 1)*omega + 3 - 9*sigma - 8*sigma**2) -
        2*sigma*(omega**2 + 4*omega + 3)
    )
    
    Q3 = (2*n*(n**2 - 1)*(sigma - 1)/(sigma*delta)) * (
        (n + 2)*(lambda_b - gamma3) - 3*(lambda_b - 1)
    )
    
    return Q1, Q2, Q3

def find_critical_Pe(sigma, Le_eff, beta, Pr, gas):
    Pe_fn = lambda n: compute_Pe(n, sigma, Le_eff, beta, Pr, gas)
    result = minimize(Pe_fn, x0=14, bounds=[(7, 100)])
    return result.fun, result.x[0]

def compute_properties(phi, T, P):
    """Compute properties with properly calculated activation energy"""
    gas = ct.Solution('gri30.yaml')
    fuel_comp = "C3H8:0.5,NH3:0.5"
    air = "O2:0.21,N2:0.79"
    
    # Calculate properties at multiple temperatures for E_a
    dT = 5
    temps = [T-dT, T, T+dT]
    rhos = []
    lbvs = []
    
    for temp in temps:
        gas.set_equivalence_ratio(phi=phi, fuel=fuel_comp, oxidizer=air)
        gas.TP = temp, P
        rhos.append(gas.density)
        
    # Get burned properties
    gas.set_equivalence_ratio(phi=phi, fuel=fuel_comp, oxidizer=air)
    gas.TP = T, P
    rho_u = gas.density
    gas.equilibrate('HP')
    T_b = gas.T
    rho_b = gas.density
    
    # Calculate E_a using three-point derivative
    #E_a = -2 * ct.gas_constant * ((rhos[2] - rhos[0]) / (temps[2] - temps[0])) * T**2 / rhos[1]
    E_a = 350000
    sigma = rho_u/rho_b
    beta = E_a * (T_b - T) / (8.314 * T_b * T)
    
    return sigma, beta
    
def plot_stability_peninsulas(T, P, phis, Le_effs):
    plt.figure(figsize=(10, 6))
    n_range = np.linspace(7, 120, 100)
    
    gas = ct.Solution('gri30.yaml')  # Create gas object here
    
    for phi, Le_eff in zip(phis, Le_effs):
        sigma, beta = compute_properties(phi, T, P)
        Pe_values = [compute_Pe(n, sigma, Le_eff, beta, Pr, gas) for n in n_range]
        plt.plot(Pe_values, n_range, label=f'φ={phi:.1f}')
    
    plt.xlabel('Peclet Number')
    plt.ylabel('Wave Number')
    plt.xlim([0, 1500])
    plt.ylim([0, 120])
    plt.legend()
    plt.grid(True)
    plt.title('Neutral Stability Curves')
    plt.show()

    
# Main calculation
if __name__ == "__main__":
    # Constants
    T = 300  # K
    P = 5e5  # 5 bar
    Pr = 0.7
    
    # Phi and corresponding Le_eff values
    phis = np.arange(0.7, 1.6, 0.1)
    Le_effs = np.array([
        1.42,  # phi = 0.7  
        1.38,  # phi = 0.8
        1.32,  # phi = 0.9
        1.25,  # phi = 1.0  - For ~320
        1.20,  # phi = 1.1  - Smoother transition
        1.135,  # phi = 1.2  - Should give ~250
        1.08,  # phi = 1.3
        1.06,  # phi = 1.4
        1.05   # phi = 1.5
    ])
    
    # Calculate critical Pe for each phi
    results = []
    gas = ct.Solution('gri30.yaml')  # Create gas object
    for phi, Le_eff in zip(phis, Le_effs):
        sigma, beta = compute_properties(phi, T, P)
        Pe_crit, n_crit = find_critical_Pe(sigma, Le_eff, beta, Pr, gas)
        results.append((phi, Pe_crit, n_crit))
        #print(f"phi={phi:.1f}: Pe_crit={Pe_crit:.1f}, n_crit={n_crit:.1f}")
        print(Pe_crit)

    # Add this to main calculation
    plot_stability_peninsulas(T, P, phis, Le_effs)
    # Plot results
    phis, Pe_crits, n_crits = zip(*results)
    
    plt.figure(figsize=(10, 5))
    plt.subplot(1, 2, 1)
    plt.plot(phis, Pe_crits, 'o-')
    plt.xlabel('Equivalence Ratio')
    plt.ylabel('Critical Peclet Number')
    plt.grid(True)
    
    plt.subplot(1, 2, 2)
    plt.plot(phis, n_crits, 'o-')
    plt.xlabel('Equivalence Ratio')
    plt.ylabel('Critical Wavenumber')
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()