using System;

namespace HttpWorker.Core.Text;

public static class UrlNormalizer
{
    public static string NormalizeInternalUrl(string url)
    {
        if (string.IsNullOrWhiteSpace(url))
        {
            return string.Empty;
        }

        try
        {
            var uri = new Uri(url.Trim());
            var scheme = uri.Scheme.ToLowerInvariant();
            if (scheme != "http" && scheme != "https")
            {
                return string.Empty;
            }

            var hostAndPort = uri.Authority.ToLowerInvariant();
            var path = uri.AbsolutePath;
            if (path != "/" && path.EndsWith('/'))
            {
                path = path.TrimEnd('/');
            }
            if (string.IsNullOrEmpty(path))
            {
                path = "/";
            }
            return $"{scheme}://{hostAndPort}{path}";
        }
        catch
        {
            return string.Empty;
        }
    }
}
