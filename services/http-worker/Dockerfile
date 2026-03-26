FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

COPY HttpWorker.sln ./
COPY src/HttpWorker.Api/HttpWorker.Api.csproj src/HttpWorker.Api/
COPY src/HttpWorker.Core/HttpWorker.Core.csproj src/HttpWorker.Core/
COPY src/HttpWorker.Services/HttpWorker.Services.csproj src/HttpWorker.Services/
COPY src/HttpWorker.Worker/HttpWorker.Worker.csproj src/HttpWorker.Worker/
COPY tests/HttpWorker.Tests/HttpWorker.Tests.csproj tests/HttpWorker.Tests/

RUN dotnet restore HttpWorker.sln

COPY . .
RUN dotnet publish src/HttpWorker.Api/HttpWorker.Api.csproj -c Release -o /app/api /p:UseAppHost=false
RUN dotnet publish src/HttpWorker.Worker/HttpWorker.Worker.csproj -c Release -o /app/worker /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app /app
ENV ASPNETCORE_URLS=http://0.0.0.0:8080
ENV SERVICE_MODE=api
EXPOSE 8080
ENTRYPOINT ["sh","-c","if [ \"$SERVICE_MODE\" = \"worker\" ]; then dotnet /app/worker/HttpWorker.Worker.dll; else dotnet /app/api/HttpWorker.Api.dll; fi"]
