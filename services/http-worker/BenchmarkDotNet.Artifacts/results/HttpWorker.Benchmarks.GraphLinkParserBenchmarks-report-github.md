```

BenchmarkDotNet v0.14.0, Windows 11 (10.0.26200.8117)
12th Gen Intel Core i5-12450H, 1 CPU, 12 logical and 8 physical cores
.NET SDK 8.0.419
  [Host]   : .NET 8.0.25 (8.0.2526.11203), X64 RyuJIT AVX2
  ShortRun : .NET 8.0.25 (8.0.2526.11203), X64 RyuJIT AVX2

Job=ShortRun  IterationCount=3  LaunchCount=1  
WarmupCount=3  

```
| Method           | InputSize | Mean         | Error        | StdDev     | Gen0     | Gen1     | Allocated  |
|----------------- |---------- |-------------:|-------------:|-----------:|---------:|---------:|-----------:|
| **FindPendingLinks** | **1000**      |     **74.48 μs** |     **39.22 μs** |   **2.150 μs** |   **5.9204** |   **0.1221** |   **36.34 KB** |
| **FindPendingLinks** | **10000**     |    **858.93 μs** |    **171.05 μs** |   **9.376 μs** |  **56.1523** |   **7.8125** |   **344.1 KB** |
| **FindPendingLinks** | **100000**    | **10,926.51 μs** | **11,528.48 μs** | **631.915 μs** | **546.8750** | **382.8125** | **3356.49 KB** |
