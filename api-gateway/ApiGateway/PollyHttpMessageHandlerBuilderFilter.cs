using Microsoft.Extensions.Http;
using System;
using System.Net.Http;
using System.Net;
using Polly;
using Polly.Extensions.Http;
using Microsoft.Extensions.Logging;  // Add this
using System.Threading.Tasks;
using Polly.Registry;

public class PollyHttpMessageHandlerBuilderFilter : IHttpMessageHandlerBuilderFilter
{
    private readonly ILogger<PollyHttpMessageHandlerBuilderFilter> _logger;
    private readonly IAsyncPolicy<HttpResponseMessage> _retryPolicy;
    private readonly IAsyncPolicy<HttpResponseMessage> _circuitBreakerPolicy;

    public PollyHttpMessageHandlerBuilderFilter(ILogger<PollyHttpMessageHandlerBuilderFilter> logger)
    {
        _logger = logger;

        // Retry Policy with logging
        _retryPolicy = HttpPolicyExtensions
            .HandleTransientHttpError()
            .RetryAsync(3, onRetry: (outcome, retryNumber, context) =>
            {
                var serviceName = context.ContainsKey("ServiceName") ? context["ServiceName"] : "unknown service";
                _logger.LogWarning($"{serviceName} returned HTTP error, try [{retryNumber}/3]");
            });

        // Circuit Breaker Policy with logging
        _circuitBreakerPolicy = HttpPolicyExtensions
            .HandleTransientHttpError()
            .CircuitBreakerAsync(1, TimeSpan.FromMinutes(1),
                onBreak: (outcome, timespan, context) =>
                {
                    var serviceName = context.ContainsKey("ServiceName") ? context["ServiceName"] : "unknown service";
                    _logger.LogError($"{serviceName} is dead ;(, redirecting request to another instance");
                },
                onReset: (context) =>
                {
                    var serviceName = context.ContainsKey("ServiceName") ? context["ServiceName"] : "unknown service";
                    _logger.LogInformation($"{serviceName} is back up, circuit breaker reset");
                });
    }

    public Action<HttpMessageHandlerBuilder> Create(Action<HttpMessageHandlerBuilder> next)
    {
        return builder =>
        {
            // Run the next handler in the pipeline
            next(builder);

            // Apply policies only to the 'game_service_cluster'
            if (builder.Name.Equals("game_service_cluster", StringComparison.OrdinalIgnoreCase))
            {
                // Add a handler to set the ServiceName in the context
                var requestContextHandler = new RequestContextHandler();

                // Wrap the handlers with Polly policies
                var retryHandler = new PolicyHttpMessageHandler(_retryPolicy)
                {
                    InnerHandler = requestContextHandler
                };

                var circuitBreakerHandler = new PolicyHttpMessageHandler(_circuitBreakerPolicy)
                {
                    InnerHandler = retryHandler
                };

                // Set the final handler chain
                requestContextHandler.InnerHandler = builder.PrimaryHandler;
                builder.PrimaryHandler = circuitBreakerHandler;
            }
        };
    }
}
