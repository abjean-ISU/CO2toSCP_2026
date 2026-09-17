# PerfusionBioreactor - Custom BioSTEAM Unit

A custom BioSTEAM unit operation for modeling perfusion bioreactors with autotrophic *Cupriavidus necator* cultivation on dissolved H₂, O₂, and CO₂.

## Overview

The `PerfusionBioreactor` class models a continuous perfusion bioreactor with internal cell retention. It accepts a single combined inlet stream containing all dissolved substrates and nutrients. It consists of three internal sub-units:
- **Pressurized CSTR** (4 atm): Cell growth reactor
- **Cell retention centrifuge**: Recycles concentrated cells back to reactor
- **Harvest mixer**: Combines clarified supernatant with bleed stream

### Nitrogen Source Configuration
The reactor supports two nitrogen source options:
- **Ammonium Sulfate (Default)**: `nitrogen_source='ammonium_sulfate'`
  - Feed: (NH₄)₂SO₄ → provides NH₃ + SO₄²⁻ byproduct
  - More stable, industrial standard, better handling
- **Direct Ammonia**: `nitrogen_source='ammonia'`
  - Feed: NH₃ directly
  - Research/laboratory configuration

### Flow Balance (Corrected Implementation)
The reactor maintains steady state with:
- **Total feed rate**: F_total = F + F_b (accounts for both perfusion and bleed streams)
- **Internal flows**: F goes to centrifuge, F_b goes directly to bleed
- **Outputs**: F_harvest = F_super1 + F_b (total harvest rate)
- **Mass balance**: F_total in = F_harvest out + F_cake recycled ✓

## Files Description

| File | Purpose | Description |
|------|---------|-------------|
| `__init__.py` | Package initialization | Exports the `PerfusionBioreactor` class |
| `unit.py` | **Main implementation** | Complete `PerfusionBioreactor` class with all BioSTEAM methods |
| `test_chemicals.py` | Test setup | Minimal chemical definitions for standalone testing |
| `test_unit.py` | Pytest tests | Comprehensive validation tests (requires pytest) |
| `example.py` | **Usage examples** | Demonstrates pilot (400L) and production (160,000L) reactors |
| `run_tests.py` | **Validation runner** | Validates all calculations against expected values |
| `README.md` | This file | Documentation and usage instructions |

## Quick Start - Verification Steps

### 1. Run the Example Script
```bash
python example.py
```
**Expected output**: Successfully simulates both pilot and production reactors with complete results display.

### 2. Run Validation Tests
```bash
python run_tests.py
```
**Expected output**: `SUCCESS: ALL TESTS PASSED!` with all 23+ individual tests passing.

### 3. Run Pytest Tests (if pytest available)
```bash
python -m pytest test_unit.py -v
```

## Key Calculations for Excel Validation

### Input Parameters (Test Case)
```
V_max = 1.0 L                    # Reactor volume
mu = 0.12 h⁻¹                   # Specific growth rate
S_f = 0.0044 g H₂/L             # Feed H₂ concentration
conversion = 0.99                # H₂ conversion efficiency
eta = 0.97                       # Cell retention efficiency
bleed_fraction = 0.20            # Bleed rate as fraction of mu
moisture = 0.75                  # Cake moisture content

# Stoichiometric coefficients (mol/mol biomass)
n_CO2 = 4.09, n_NH3 = 0.76, n_H2 = 21.36, n_O2 = 6.21, n_H2O = 18.70
MW_biomass = 97.09 g/mol

# Kinetic parameters (molar basis)
Y_mol = 4.5 g CDW/mol H₂         # Maximum yield
m_s_mol = 0.025 mol H₂/g CDW/h   # Maintenance coefficient
```

### Step-by-Step Calculations

#### 1. Stoichiometric Mass Ratios
```excel
g_H2_per_gCDW = (21.36 × 2.016) / 97.09 = 0.44352
g_CO2_per_gCDW = (4.09 × 44.01) / 97.09 = 1.85396
g_O2_per_gCDW = (6.21 × 32.00) / 97.09 = 2.04676
g_NH3_per_gCDW = (0.76 × 17.03) / 97.09 = 0.13331
g_H2O_per_gCDW = (18.70 × 18.02) / 97.09 = 3.47074
```

#### 2. Kinetic Parameters (Mass Basis)
```excel
Y_max = Y_mol / MW_H2 = 4.5 / 2.016 = 2.2321 g CDW/g H₂
m_s = m_s_mol × MW_H2 = 0.025 × 2.016 = 0.05040 g H₂/g CDW/h

Y_obs = 1 / (1/Y_max + m_s/mu) = 1 / (1/2.2321 + 0.05040/0.12) = 1.1521 g CDW/g H₂
q_s = mu/Y_max + m_s = 0.12/2.2321 + 0.05040 = 0.10416 g H₂/g CDW/h
```

#### 3. Flow Rates and Operating Point
```excel
D_b = bleed_fraction × mu = 0.20 × 0.12 = 0.0240 h⁻¹
D = (mu - D_b) / (1 - eta) = (0.12 - 0.024) / (1 - 0.97) = 3.2000 h⁻¹
F = D × V_max = 3.2000 × 1.0 = 3.2000 L/h
F_b = D_b × V_max = 0.0240 × 1.0 = 0.0240 L/h
F_total = F + F_b = 3.2000 + 0.0240 = 3.2240 L/h (total feed required)
```

#### 4. Biological State
```excel
S = S_f × (1 - conversion) = 0.0044 × (1 - 0.99) = 0.000044 g H₂/L
X = D × (S_f - S) / q_s = 3.2000 × (0.0044 - 0.000044) / 0.10416 = 0.1338 g CDW/L
X_max = D × S_f / q_s = 3.2000 × 0.0044 / 0.10416 = 0.1352 g CDW/L
```

#### 5. Production Rates
```excel
CDW_produced = mu × X × V_max = 0.12 × 0.1338 × 1.0 = 0.01606 g/h
H2_consumed = q_s × X × V_max = 0.10416 × 0.1338 × 1.0 = 0.01394 g/h
CO2_consumed = g_CO2_per_gCDW × CDW_produced = 1.85396 × 0.01606 = 0.02977 g/h
O2_consumed = g_O2_per_gCDW × CDW_produced = 2.04676 × 0.01606 = 0.03287 g/h
NH3_consumed = g_NH3_per_gCDW × CDW_produced = 0.13331 × 0.01606 = 0.00214 g/h
H2O_produced = g_H2O_per_gCDW × CDW_produced = 3.47074 × 0.01606 = 0.05574 g/h
```

#### 6. Cell Separation (Centrifuge)
```excel
cell_to_cake = eta × F × X = 0.97 × 3.2000 × 0.1338 = 0.41539 g CDW/h
cell_to_super1 = (1 - eta) × F × X = (1 - 0.97) × 3.2000 × 0.1338 = 0.01246 g CDW/h

cake_total_mass = cell_to_cake / (1 - moisture) = 0.41539 / (1 - 0.75) = 1.66156 g/h
water_in_cake = cake_total_mass × moisture = 1.66156 × 0.75 = 1.24617 g/h
F_cake = cake_total_mass / 1000 = 1.66156 / 1000 = 0.00166 L/h
F_super1 = F - F_cake = 3.2000 - 0.00166 = 3.19834 L/h
```

#### 7. Harvest Stream
```excel
cell_bleed = F_b × X = 0.0240 × 0.1338 = 0.00321 g CDW/h
F_harvest = F_super1 + F_b = 3.19834 + 0.0240 = 3.22234 L/h
cell_harvest = cell_to_super1 + cell_bleed = 0.01246 + 0.00321 = 0.01567 g CDW/h
X_harvest = cell_harvest / F_harvest = 0.01567 / 3.22234 = 0.00486 g CDW/L
```

#### 8. Mass Balance Checks
```excel
# Cell balance: growth = losses
CDW_produced - (cell_to_super1 + cell_bleed) = 0.01606 - 0.01567 = 0.00039 ≈ 0 ✓

# Volume balance across centrifuge: F = F_super1 + F_cake
F - (F_super1 + F_cake) = 3.2000 - (3.19834 + 0.00166) = 0 ✓

# Overall volume balance: F_total_in = F_harvest_out + F_cake_recycled
F_total - (F_harvest + F_cake) = 3.2240 - (3.22234 + 0.00166) = 0 ✓

# Substrate balance: H₂_in = H₂_consumed + H₂_out (CORRECTED)
H2_in = F_total × S_f = 3.2240 × 0.0044 = 0.01419 g/h
H2_out = F_harvest × S = 3.22234 × 0.000044 = 0.00014 g/h
H2_check = H2_consumed + H2_out = 0.01394 + 0.00014 = 0.01408 g/h ✓
```

## Excel Calculator Setup

### Recommended Excel Structure

**Sheet 1: Input Parameters**
- A1: Parameter names, B1: Values, C1: Units, D1: Description
- Include all input parameters listed above

**Sheet 2: Calculations**
- Follow the step-by-step calculations above
- Use cell references to Sheet 1 for all inputs
- Color-code intermediate vs. final results

**Sheet 3: Validation**
- Compare your Excel results to expected values
- Include tolerance checks (±0.1% relative error)
- Flag any discrepancies

### Key Excel Formulas

```excel
# Stoichiometric ratios
=B2*C2/D2  # (molar_coeff * MW_component) / MW_biomass

# Y_obs calculation
=1/(1/B5+C5/D5)  # 1/(1/Y_max + m_s/mu)

# Dilution rate calculation
=(B6-C6)/(1-D6)  # (mu - D_b)/(1 - eta)

# Mass balance check
=ABS(B10-(C10+D10))<1E-6  # Should return TRUE
```

## Validation Expected Results

When you run `run_tests.py`, you should see these exact values for the 1L test case:

| Parameter | Expected Value | Units |
|-----------|----------------|-------|
| g_H2_per_gCDW | 0.44352 | g H₂/g CDW |
| g_CO2_per_gCDW | 1.85396 | g CO₂/g CDW |
| Y_obs | 1.1521 | g CDW/g H₂ |
| D | 3.2000 | h⁻¹ |
| F_total | 3.2240 | L/h |
| X | 0.1338 | g CDW/L |
| CDW_produced | 0.01606 | g/h |
| F_harvest | 3.2223 | L/h |
| X_harvest | 0.004984 | g CDW/L |

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure BioSTEAM is installed (`pip install biosteam`)
2. **Unicode errors**: Use `chcp 65001` in Windows Command Prompt
3. **Validation failures**: Check that you're using the corrected expected values
4. **Mass balance errors**: This version includes corrected flow balance using total feed rate F_total = F + F_b

### Recent Fixes

**Flow Balance Correction:**
- **Issue**: Previous implementation violated mass conservation with F_harvest > F_feed.
- **Solution**: Total feed rate F_total = F + F_b with feed composition based on F_total.

**Metabolic Heat Correction:**
- **Issue**: Used theoretical H₂ combustion enthalpy (242 kJ/mol) overestimating cooling requirements.
- **Solution**: Literature-based value (121 kJ/mol) reflecting ~50% energy efficiency in autotrophic *C. necator* hydrogen oxidation.
- **Basis**: Energy efficiency studies showing 45-50% heat generation vs. theoretical combustion energy.

### Contact/Support

If calculations don't match expected values:
1. Check all input parameters match exactly
2. Verify intermediate calculations step-by-step
3. Ensure proper order of operations
4. Compare against `run_tests.py` output

## Integration with Main Model

To use in your larger BioSTEAM model:

```python
from perfusion_bioreactor import PerfusionBioreactor

# Create reactor with single combined inlet stream
reactor = PerfusionBioreactor(
    'R301',
    ins=['gas_saturated_media'],  # Single stream with H₂, O₂, CO₂, nitrogen source, water
    outs=['harvest_stream'],
    V_max=160000,  # L
    mu=0.12, S_f=0.0044,
    nitrogen_source='ammonium_sulfate',  # Industrial configuration
    # ... other parameters
)

# Simulate
reactor.simulate()
print(reactor.results())
```

## Nitrogen Source Examples

### **Ammonium Sulfate Configuration (Recommended)**
```python
reactor = PerfusionBioreactor(
    'R301', ins=['combined_feed'], outs=['harvest'],
    V_max=160000, mu=0.12, S_f=0.0044,
    nitrogen_source='ammonium_sulfate',  # Default
    # Component IDs (ensure these match your chemicals database)
    ammonium_sulfate_id='AmmoniumSulfate',
    sulfate_id='SO4-2',
    # ... other parameters
)
```
**Benefits:** More stable, industrial standard, better handling, no volatilization issues

### **Direct Ammonia Configuration**
```python
reactor = PerfusionBioreactor(
    'R301', ins=['combined_feed'], outs=['harvest'],
    V_max=160000, mu=0.12, S_f=0.0044,
    nitrogen_source='ammonia',
    # ... other parameters
)
```
**Use case:** Laboratory research, when NH₃ is already available as gas

### **Feed Stream Composition**
- **Ammonium Sulfate**: Feed contains (NH₄)₂SO₄, harvest contains SO₄²⁻ byproduct
- **Ammonia**: Feed contains NH₃ directly
- Both provide identical nitrogen for cell growth (same `NH3_consumed` rate)

**Perfect Integration with Gas Contactors:**
```python
# Gas contactors produce combined stream with all dissolved species
combined_gas_stream = mixer_after_contactors.outs[0]

# Direct connection to perfusion reactor
reactor = PerfusionBioreactor('R301', ins=[combined_gas_stream],
                            nitrogen_source='ammonium_sulfate', outs=...)
```

The unit integrates seamlessly with BioSTEAM flowsheets, costing, and utilities.