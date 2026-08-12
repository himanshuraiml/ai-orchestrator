from prometheus_client import Counter, Histogram

task_total = Counter("task_total", "Tasks received, by terminal status", ["status"])

model_calls_total = Counter(
    "model_calls_total", "Model invocations, by model id and status", ["model_id", "status"]
)

execution_cost_usd_total = Counter(
    "execution_cost_usd_total", "Cumulative model execution cost in USD", ["model_id"]
)

execution_latency_ms = Histogram(
    "execution_latency_ms",
    "Model execution latency in milliseconds",
    ["model_id"],
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000),
)
