```

BenchmarkDotNet v0.14.0, Windows 11 (10.0.26200.8117)
12th Gen Intel Core i5-12450H, 1 CPU, 12 logical and 8 physical cores
.NET SDK 8.0.419
  [Host]   : .NET 8.0.25 (8.0.2526.11203), X64 RyuJIT AVX2
  ShortRun : .NET 8.0.25 (8.0.2526.11203), X64 RyuJIT AVX2

Job=ShortRun  IterationCount=3  LaunchCount=1  
WarmupCount=3  

```
| Method       | Count | Mean        | Error        | StdDev       | Gen0     | Allocated |
|------------- |------ |------------:|-------------:|-------------:|---------:|----------:|
| **NormalizeAll** | **100**   |    **71.47 μs** |     **73.22 μs** |     **4.014 μs** |   **7.9346** |  **48.92 KB** |
| **NormalizeAll** | **1000**  |   **661.48 μs** |    **151.86 μs** |     **8.324 μs** |  **80.0781** | **494.23 KB** |
| **NormalizeAll** | **10000** | **5,003.57 μs** | **19,090.81 μs** | **1,046.432 μs** | **804.6875** | **4970.8 KB** |
