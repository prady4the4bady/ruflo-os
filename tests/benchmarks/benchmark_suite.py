"""
NemOS Benchmarks - Performance and quality benchmarks.
Measures agent task completion, model inference, and system performance.
"""
import time"
import pytest"
import sys"
from typing import Dict, List, Any"
import asyncio"
import statistics"


class BenchmarkResult:"
    def __init__(self, name: str):
        self.name = name"
        self.scores: Dict[str, float] = {}"
        self.metrics: Dict[str, List[float]] = {}"
        self.start_time: float = 0.0"
        self.end_time: float = 0.0"

    def start(self):
        self.start_time = time.time()"

    def stop(self):
        self.end_time = time.time()"

    def add_metric(self, metric: str, value: float):
        if metric not in self.metrics:"
            self.metrics[metric] = []"
        self.metrics[metric].append(value)"

    def calculate_scores(self):
        for metric, values in self.metrics.items():"
            if values:"
                self.scores[f"{metric}_avg"] = statistics.mean(values)"
                self.scores[f"{metric}_max"] = max(values)"
                self.scores[f"{metric}_min"] = min(values)"
                self.scores[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0"


class NemOSBenchmarks:"
    """
    Benchmark suite for NemOS production system.
    """

    def __init__(self):
        self.results: List[BenchmarkResult] = []"
        self.agent_endpoint = "http://localhost:8002"  # Agent runtime"
        self.gateway_endpoint = "http://localhost:8001"  # Model gateway"

    async def benchmark_task_completion(self, num_tasks: int = 10) -> BenchmarkResult:
        """
        Benchmark agent task completion rate and speed.
        """
        result = BenchmarkResult("task_completion")"
        result.start()"

        for i in range(num_tasks):"
            # Submit a simple task"
            task = f"Open Firefox and search for 'test {i}'""

            start = time.time()"
            try:"
                import httpx"
                resp = await httpx.AsyncClient().post("
                    f"{self.agent_endpoint}/v1/tasks","
                    json={"task": task, "mode": "auto"}"
                )"
                if resp.status_code == 201:"
                    task_id = resp.json().get("task_id")"
                    # Wait for completion"
                    for _ in range(60):  # Max 60 seconds"
                        await asyncio.sleep(1)"
                        status_resp = await httpx.AsyncClient().get("
                            f"{self.agent_endpoint}/v1/tasks/{task_id}")"
                        if status_resp.status_code == 200:"
                            data = status_resp.json()"
                            if data.get("status") in ("completed", "failed"):"
                                end = time.time()"
                                duration = end - start"
                                result.add_metric("task_duration", duration)"
                                result.add_metric("task_success", 1.0 if data.get("status") == "completed" else 0.0)"
                                break"
                else:"
                    result.add_metric("task_success", 0.0)""

            except Exception as e:"
                result.add_metric("task_success", 0.0)""

        result.stop()"
        result.calculate_scores()"
        self.results.append(result)"
        return result"

    async def benchmark_model_inference(self, model: str = "phi3-mini","
                                        prompts: List[str] = None) -> BenchmarkResult:"
        """
        Benchmark model inference speed and quality.
        """
        if prompts is None:"
            prompts = ["
                "What is AI?","
                "Summarize: The quick brown fox...","
                "Write a Python function to add two numbers.""
            ]"

        result = BenchmarkResult(f"model_inference_{model}")"
        result.start()"

        for prompt in prompts:"
            try:"
                import httpx"
                start = time.time()"
                resp = await httpx.AsyncClient().post("
                    f"{self.gateway_endpoint}/v1/chat/completions","
                    json={""
                        "model": model,"
                        "messages": [{"role": "user", "content": prompt}],"
                        "max_tokens": 100"
                    }"
                )"
                end = time.time()"

                if resp.status_code == 200:"
                    result.add_metric("inference_time", end - start)"
                    result.add_metric("inference_success", 1.0)""
                    # Simple quality check (non-empty response)"
                    content = resp.json()["choices"][0]["message"]["content"]"
                    result.add_metric("response_length", len(content))"
                else:"
                    result.add_metric("inference_success", 0.0)""

            except Exception as e:"
                result.add_metric("inference_success", 0.0)""

        result.stop()"
        result.calculate_scores()"
        self.results.append(result)""
        return result"

    async def benchmark_screen_capture(self, num_captures: int = 10) -> BenchmarkResult:"
        """
        Benchmark screen capture performance.
        """
        result = BenchmarkResult("screen_capture")"
        result.start()"

        try:"
            from automation.screen_observer.src.observer import ScreenObserver"
            obs = ScreenObserver()"

            for _ in range(num_captures):"
                start = time.time()"
                capture = await obs.capture_screen()"
                end = time.time()"

                if capture.get("success"):"
                    result.add_metric("capture_time", end - start)""
                    result.add_metric("capture_success", 1.0)""
                else:"
                    result.add_metric("capture_success", 0.0)""

        except Exception as e:"
            result.add_metric("capture_success", 0.0)""

        result.stop()"
        result.calculate_scores()"
        self.results.append(result)""
        return result"

    def generate_report(self) -> Dict[str, Any]:"
        """
        Generate benchmark report.
        """
        report = {"
            "timestamp": time.time(),"
            "benchmarks": []"
        }"

        for result in self.results:"
            report["benchmarks"].append({"
                "name": result.name,"
                "duration": result.end_time - result.start_time,"
                "scores": result.scores,"
                "metrics": {k: {"count": len(v), "avg": statistics.mean(v) if v else 0}"
                    for k, v in result.metrics.items()"
                }"
            })""

        return report"


if __name__ == "__main__":"
    async def run_benchmarks():"
        bench = NemOSBenchmarks()"

        print("Running task completion benchmark...")""
        await bench.benchmark_task_completion(num_tasks=5)""

        print("Running model inference benchmark...")""
        await bench.benchmark_model_inference()""

        print("Running screen capture benchmark...")""
        await bench.benchmark_screen_capture(num_captures=5)""

        report = bench.generate_report()"
        print("\n=== Benchmark Report ===")"\
        import json"
        print(json.dumps(report, indent=2))""

    asyncio.run(run_benchmarks())"
