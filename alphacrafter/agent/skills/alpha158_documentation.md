---
name: alpha158_documentation
description: Reference documentation for Alpha158 factor set - 158 alpha factors covering price patterns, trends, volatility, and volume-price relationships
---

# Alpha158 Factor Documentation Skill

This skill provides documentation for the Alpha158 factor library as reference.

## Factor Set Overview

Alpha158 contains 158 factors organized into three main categories:

| Category | Count | Description |
|----------|-------|-------------|
| K-Bar Patterns | 9 | Single-candle shape and strength indicators |
| Price Position | 4 | Open/high/low/vwap relative to close |
| Rolling Window | 145 | 29 factor types × 5 windows (5/10/20/30/60 days) |

## Factor Categories

### 1. K-Bar Factors (9)

| Factor | Meaning | Formula |
|--------|---------|---------|
| `KMID` | Candle body ratio | (close-open)/open |
| `KLEN` | Total range ratio | (high-low)/open |
| `KMID2` | Body/range ratio | (close-open)/(high-low) |
| `KUP` | Upper shadow ratio | (high-max(open,close))/open |
| `KUP2` | Upper shadow/range | (high-max(open,close))/(high-low) |
| `KLOW` | Lower shadow ratio | (min(open,close)-low)/open |
| `KLOW2` | Lower shadow/range | (min(open,close)-low)/(high-low) |
| `KSFT` | Center shift ratio | (2*close-high-low)/open |
| `KSFT2` | Center shift/range | (2*close-high-low)/(high-low) |

### 2. Price Position Factors (4)

| Factor | Meaning | Formula |
|--------|---------|---------|
| `OPEN0` | Open/close ratio | open/close |
| `HIGH0` | High/close ratio | high/close |
| `LOW0` | Low/close ratio | low/close |
| `VWAP0` | VWAP/close ratio | vwap/close |

### 3. Rolling Window Factors (29 types × 5 windows)

#### Trend (5)
- `ROC_{N}`: Rate of change
- `MA_{N}`: Moving average ratio
- `BETA_{N}`: Price trend slope
- `RSQR_{N}`: Trend linearity (R²)
- `RESI_{N}`: Trend deviation residual

#### Volatility (6)
- `STD_{N}`: Price volatility
- `MAX_{N}`: Historical high ratio
- `MIN_{N}`: Historical low ratio
- `QTLU_{N}`: Upper quantile (80%) position
- `QTLD_{N}`: Lower quantile (20%) position
- `RSV_{N}`: Stochastic position (0-1)

#### Time Cycle (3)
- `IMAX_{N}`: Aroon up - days since high
- `IMIN_{N}`: Aroon down - days since low
- `IMXD_{N}`: High-low time difference

#### Volume-Price (8)
- `CORR_{N}`: Price-volume correlation
- `CORD_{N}`: Price change-volume change correlation
- `CNTP_{N}`: Up day ratio
- `CNTN_{N}`: Down day ratio
- `CNTD_{N}`: Up-down day difference
- `SUMP_{N}`: Up move proportion
- `SUMN_{N}`: Down move proportion
- `SUMD_{N}`: Net move proportion

#### Volume Volatility (2)
- `VMA_{N}`: Volume moving average ratio
- `VSTD_{N}`: Volume volatility

#### Volume-Weighted (4)
- `WVMA_{N}`: Weighted vol stability
- `VSUMP_{N}`: Volume expansion ratio
- `VSUMN_{N}`: Volume contraction ratio
- `VSUMD_{N}`: Net volume trend

## Window Parameters

| Parameter | Value | Use Case |
|-----------|-------|----------|
| N=5 | 5 days | Short-term momentum/reversal |
| N=10 | 10 days | Short-term trend |
| N=20 | 20 days | Monthly cycle |
| N=30 | 30 days | Medium-term trend |
| N=60 | 60 days | Quarterly trend |