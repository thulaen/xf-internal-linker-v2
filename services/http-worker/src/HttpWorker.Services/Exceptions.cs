namespace HttpWorker.Services;

public class HttpWorkerException(string message) : Exception(message);

public sealed class ValidationException(string message) : HttpWorkerException(message);

public sealed class BlockedUrlException() : HttpWorkerException("blocked url");

public sealed class MalformedSitemapException() : HttpWorkerException("malformed sitemap xml");
