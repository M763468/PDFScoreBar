
# Technical Debt & Optimization Notes

## 1. Performance Optimization
- **Real-ESRGAN Latency**: Currently ~45s/page (x4).
  - **Issue**: Model might be re-initialized unnecessarily if wrapped in scripts called multiple times.
  - **Potential Fix**: 
    - Ensure model loading happens once (singleton or server mode).
    - Verify GPU utilization (is it actually using CUDA efficiently?).
    - Investigate tiling or ROI-based Super-Resolution (only upscale relevant areas).
- **Parallelization**: 
  - Processing multiple pages or even multiple staves within a page could be parallelized to reduce total turnaround time.

## 2. Infrastructure
- **Hybrid Pipeline**: Currently requires running 3 separate scripts (`homr` evaluation, `homr` SR evaluation, `OMR-DLN` SR evaluation) and then a merger script.
  - **Future Goal**: Create a unified Class/API that manages this flow efficiently, potentially keeping models in memory.

## 3. Alternative Approaches
- **Lighter SR**: If `Real-ESRGAN` proves too heavy for production, explore lighter models (e.g., specific document-optimized GANs) but strictly verify they don't degrade detection performance.
