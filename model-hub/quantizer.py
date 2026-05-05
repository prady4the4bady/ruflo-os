"""
Model Quantizer - Quantize models to GGUF using llama.cpp.
Supports Q4_K_M, Q5_K_M, Q8_0 quantization types.
"""
import argparse
import sys"
import os"
import subprocess"
import structlog"

logger = structlog.get_logger(__name__)


def check_llama_cpp() -> bool:
    """Check if llama.cpp quantize binary is installed."""
    try:
        result = subprocess.run(
            ["which", "quantize"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return True

        # Check common llama.cpp build paths
        common_paths = [
            "/opt/llama.cpp/build/bin/quantize",
            str(Path.home() / ".local/bin/quantize"),
            "llama.cpp/build/bin/quantize"
        ]
        for path in common_paths:
            if os.path.exists(path):
                return True

        logger.warning("llama.cpp quantize binary not found")
        return False
    except Exception as e:
        logger.error("llama.cpp check failed", error=str(e))
        return False


def quantize(
    model_path: str,
    bits: int = 4,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Quantize model to GGUF.
    bits: 4 (Q4_K_M), 5 (Q5_K_M), 8 (Q8_0)
    """
    if not os.path.exists(model_path):
        return {"success": False, "error": f"Model not found: {model_path}"}

    # Map bits to quantization type
    qmap = {
        4: "Q4_K_M",
        5: "Q5_K_M",
        8: "Q8_0"
    }
    qtype = qmap.get(bits, "Q4_K_M")

    # Determine output path
    if output_path is None:
        base = os.path.splitext(model_path)[0]
        output_path = f"{base}-{qtype}.gguf"

    # Find quantize binary
    quantize_bin = "quantize"
    if not check_llama_cpp():
        # Try to find it
        for path in ["/opt/llama.cpp/build/bin/quantize",
                   os.path.expanduser("~/.local/bin/quantize")]:
            if os.path.exists(path):
                quantize_bin = path
                break
        else:
            return {
                "success": False,
                "error": "llama.cpp quantize binary not found. Install from https://github.com/ggerganov/llama.cpp"
            }

    try:
        # Get original size
        orig_size = os.path.getsize(model_path) / (1024 ** 3)  # GB

        logger.info(
            "Starting quantization",
            model=model_path,
            bits=bits,
            type=qtype
        )

        # Run quantize
        result = subprocess.run(
            [quantize_bin, model_path, output_path, qtype],
            capture_output=True, text=True, timeout=3600
        )

        if result.returncode == 0:
            quantized_size = os.path.getsize(output_path) / (1024 ** 3)
            compression = orig_size / quantized_size if quantized_size > 0 else 0

            info = {
                "success": True,
                "original_path": model_path,
                "quantized_path": output_path,
                "original_size_gb": round(orig_size, 2),
                "quantized_size_gb": round(quantized_size, 2),
                "compression_ratio": round(compression, 2),
                "quantization_type": qtype,
                "bits": bits
            }

            logger.info("Quantization complete", **info)
            return info
        else:
            return {
                "success": False,
                "error": result.stderr,
                "stdout": result.stdout
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Quantization timed out (1hr)"}
    except Exception as e:
        logger.error("Quantization failed", error=str(e))
        return {"success": False, "error": str(e)}


def auto_detect_llama_cpp() -> bool:
    """Auto-detect if llama.cpp is installed."""
    try:
        result = subprocess.run(
            ["bash", "-c", "source ~/.bashrc 2>/dev/null; which quantize"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Quantize models to GGUF")
    parser.add_argument(
        "model_path",
        help="Path to input model (safetensors or pytorch)"
    )
    parser.add_argument(
        "--bits",
        type=int,
        choices=[4, 5, 8],
        default=4,
        help="Quantization bits (4=Q4_K_M, 5=Q5_K_M, 8=Q8_0)"
    )
    parser.add_argument(
        "--output",
        help="Output path (default: <model>_Qx_K_M.gguf)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.model_path):
        print(f"Error: Model not found: {args.model_path}")
        sys.exit(1)

    print(f"Quantizing {args.model_path} to {args.bits}-bit GGUF...")
    result = quantize(args.model_path, args.bits, args.output)

    if result["success"]:
        print("✓ Quantization complete!")
        print(f"  Original: {result['original_size_gb']} GB")
        print(f"  Quantized: {result['quantized_size_gb']} GB")
        print(f"  Output: {result['quantized_path']}")
        print(f"  Compression: {result['compression_ratio']}x")
        sys.exit(0)
    else:
        print(f"✗ Quantization failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
