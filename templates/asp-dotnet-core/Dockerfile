#See https://aka.ms/containerfastmode to understand how Visual Studio uses this Dockerfile to build your images for faster debugging.

FROM mcr.microsoft.com/dotnet/aspnet:3.1 AS base
WORKDIR /app
EXPOSE 80

FROM mcr.microsoft.com/dotnet/sdk:3.1 AS build
WORKDIR /src
COPY ["app/ASP-MVC-example.csproj", "app/"]
RUN dotnet restore "app/ASP-MVC-example.csproj"
COPY app /src/app
RUN ls
WORKDIR "/src/app"
RUN ls
RUN dotnet build "ASP-MVC-example.csproj" -c Release -o /app/build

FROM build AS publish
RUN dotnet publish "ASP-MVC-example.csproj" -c Release -o /app/publish

FROM base AS final
WORKDIR /app
COPY --from=publish /app/publish .
ENTRYPOINT ["dotnet", "ASP-MVC-example.dll"]
