using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Yarp.ReverseProxy;
using Polly;
using Polly.Extensions.Http;
using System;
using System.Net;
using System.Net.Http;

var builder = WebApplication.CreateBuilder(args);

// Add CORS services
builder.Services.AddCors(options =>
{
    options.AddPolicy("CorsPolicy", builder =>
    {
        builder.WithOrigins("http://localhost:8000", "http://localhost:5500") // Replace with your client origin
               .AllowAnyMethod()
               .AllowAnyHeader()
               .AllowCredentials();
    });
});

// Configure the retry and circuit breaker policies
var retryPolicy = HttpPolicyExtensions
    .HandleTransientHttpError()
    .OrResult(msg => msg.StatusCode == HttpStatusCode.InternalServerError)
    .RetryAsync(3);

var circuitBreakerPolicy = HttpPolicyExtensions
    .HandleTransientHttpError()
    .OrResult(msg => msg.StatusCode == HttpStatusCode.InternalServerError)
    .CircuitBreakerAsync(1, TimeSpan.FromMinutes(1));

// Register a named HttpClient for the cluster and apply the policies
builder.Services.AddHttpClient("game_service_cluster")
    .AddPolicyHandler(retryPolicy)
    .AddPolicyHandler(circuitBreakerPolicy);

builder.Services.AddReverseProxy()
    .LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"));

// Add controllers if needed
builder.Services.AddControllers();

// Add Swagger for documentation
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Configure Kestrel to listen on any IP address and port 5029
builder.WebHost.ConfigureKestrel(serverOptions =>
{
    serverOptions.ListenAnyIP(5029);
});

var app = builder.Build();

// Use CORS policy
app.UseCors("CorsPolicy");

app.UseSwagger();
app.UseSwaggerUI();

// Use HTTPS redirection
app.UseHttpsRedirection();

// Use Authorization
app.UseAuthorization();

// Map controllers
app.MapControllers();

// Enable the reverse proxy
app.MapReverseProxy();

app.Run();
