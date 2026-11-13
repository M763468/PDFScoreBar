"""torch(cu130) + ORT(cu12) in one process, both orders, with real kernels."""
import glob, os, sys, sysconfig
import numpy as np

order = sys.argv[1]
def torch_conv():
    import torch
    torch.backends.cudnn.enabled = True
    x = torch.randn(1, 3, 64, 64, device="cuda")
    y = torch.nn.Conv2d(3, 8, 3).cuda()(x)
    torch.cuda.synchronize()
    return f"torch conv ok cudnn={torch.backends.cudnn.version()}"
def ort_run():
    import onnxruntime as ort
    import torch; ort.preload_dlls(cuda=False, cudnn=False, msvc=False) if False else None
    model = sorted(glob.glob(os.path.join(sysconfig.get_paths()["purelib"], "homr", "segmentation", "segnet*.onnx")))[0]
    s = ort.InferenceSession(model, providers=[("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"})])
    i = s.get_inputs()[0]
    shape = [d if isinstance(d, int) else 1 for d in i.shape]
    shape = [1, shape[1] if shape[1] else 1] + [320, 320] if len(shape) == 4 else shape
    dtype = np.float16 if "float16" in i.type else np.float32
    s.run(None, {i.name: np.zeros(shape, dtype)})
    return f"ort providers={s.get_providers()}"
steps = [torch_conv, ort_run] if order == "torch-first" else [ort_run, torch_conv]
for f in steps:
    print(f())
import ctypes, ctypes.wintypes, psutil
p = psutil.Process()
print("cudnn64_9 modules:", sorted({m.path for m in p.memory_maps() if "cudnn64_9" in m.path.lower()}))
