# Используем официальный образ .NET SDK для сборки
FROM mcr.microsoft.com/dotnet/sdk:8.0@sha256:35792ea4ad1db051981f62b313f1be3b46b1f45cadbaa3c288cd0d3056eefb83 AS build
WORKDIR /src

# Копируем файл решения (.sln) и файл проекта (.csproj)
COPY ApiGateway.sln ./
COPY ApiGateway/ApiGateway.csproj ApiGateway/

# Восстанавливаем зависимости
RUN dotnet restore

# Копируем остальные файлы проекта
COPY ApiGateway/ ApiGateway/

# Устанавливаем рабочую директорию на проекте
WORKDIR /src/ApiGateway

# Публикуем приложение
RUN dotnet publish -c Release -o /app/publish

# Используем официальный образ .NET Runtime для запуска
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .

# Открываем порт 5029 для доступа к приложению
EXPOSE 5029

# Запускаем приложение
ENTRYPOINT ["dotnet", "ApiGateway.dll"]
