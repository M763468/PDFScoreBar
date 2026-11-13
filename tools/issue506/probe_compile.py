import sys, time, torch
mode = sys.argv[1] if len(sys.argv) > 1 else "reduce-overhead"
m = torch.nn.Sequential(torch.nn.Conv2d(3, 16, 3, padding=1), torch.nn.LeakyReLU(), torch.nn.Conv2d(16, 3, 3, padding=1)).cuda().eval()
x = torch.randn(1, 3, 128, 128, device="cuda")
with torch.inference_mode():
    ref = m(x)
    c = torch.compile(m, mode=mode)
    t = time.time(); out = c(x); torch.cuda.synchronize()
    print("compile ok", mode, f"{time.time()-t:.1f}s", "maxdiff", (out - ref).abs().max().item())
