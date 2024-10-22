# Stage 1: Build the application
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build

# Set the working directory inside the container
WORKDIR /src

# Copy the solution and project files
COPY ApiGateway/ApiGateway.csproj ApiGateway/

# Установка переменной окружения для ASP.NET Core
ENV ASPNETCORE_URLS=http://+:5029

# Restore the dependencies
RUN dotnet restore ApiGateway/ApiGateway.csproj

# Copy the remaining source code
COPY ApiGateway/ ApiGateway/

# Navigate to the project directory
WORKDIR /src/ApiGateway

# Publish the application in Release mode
RUN dotnet publish -c Release -o /app/publish

# Stage 2: Create the runtime image
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime

# Set the working directory inside the container
WORKDIR /app

# Copy the published output from the build stage
COPY --from=build /app/publish .

# Expose the actual port the app listens on
EXPOSE 5029


# Entry point for the container
ENTRYPOINT ["dotnet", "ApiGateway.dll"]
