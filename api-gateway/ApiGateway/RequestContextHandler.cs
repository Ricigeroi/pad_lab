using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Polly;

public class RequestContextHandler : DelegatingHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        // Create a new context or use the existing one
        if (!request.Properties.ContainsKey("PolicyExecutionContext"))
        {
            request.Properties["PolicyExecutionContext"] = new Context();
        }

        var context = (Context)request.Properties["PolicyExecutionContext"];
        // Add service name to context
        context["ServiceName"] = request.RequestUri.Host;

        // Proceed with the request
        return await base.SendAsync(request, cancellationToken);
    }
}
