"""Create a real CUDA EP session on a HOMR model; listing providers is not evidence."""
import glob, os, sys, sysconfig
import onnxruntime as ort

if "--torch-first" in sys.argv:
    import torch  # noqa: F401
if "--preload" in sys.argv:
    ort.preload_dlls(directory="")
model = sorted(glob.glob(os.path.join(sysconfig.get_paths()["purelib"], "homr", "**", "segnet*.onnx"), recursive=True))[0]
s = ort.InferenceSession(model, providers=[("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"})])
print("MODEL", os.path.basename(model), "SESSION_PROVIDERS", s.get_providers())
