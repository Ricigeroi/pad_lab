# Используем официальный образ .NET SDK для сборки
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Копируем файл решения (.sln)
COPY ApiGateway.sln ./

# Копируем файл проекта (.csproj)
COPY ApiGateway/ApiGateway.csproj ApiGateway/ApiGateway.csproj

# Восстанавливаем зависимости
RUN dotnet restore ApiGateway.sln

# Копируем остальные файлы проекта
COPY . .

# Устанавливаем рабочую директорию на проекте
WORKDIR /src/ApiGateway

# Публикуем приложение
RUN dotnet publish -c Release -o /app/publish

# Используем официальный образ .NET Runtime для запуска
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "ApiGateway.dll"]
