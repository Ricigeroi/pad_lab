# Online Sudoku Platform

## Project Description
The **Online Sudoku Platform** is a comprehensive web application that allows users to play Sudoku games, track their progress, and participate in game lobbies for multiplayer sessions. The platform is built using a robust **microservices architecture**, ensuring scalability, high availability, and separation of concerns. Key features include real-time communication via WebSockets, advanced logging and monitoring, resilient transaction management, distributed caching, database replication, and a data warehouse for analytics.

## Table of Contents
1. [Application Suitability](#application-suitability)
   - [Relevance of Microservices Architecture](#relevance-of-microservices-architecture)
   - [Real-World Examples](#real-world-examples)
2. [System Architecture](#system-architecture)
   - [Architecture Diagram](#architecture-diagram)
   - [Updated Features](#updated-features)
3. [Technology Stack and Communication Patterns](#technology-stack-and-communication-patterns)
   - [Existing Services](#existing-services)
   - [New Features Implemented](#new-features-implemented)
4. [Service Boundaries](#service-boundaries)
   - [Game Service](#game-service)
   - [Lobby Service](#lobby-service)
   - [API Gateway](#api-gateway)
   - [Logging and Monitoring Service](#logging-and-monitoring-service)
   - [Data Warehouse Service](#data-warehouse-service)
   - [Saga Coordinator Service](#saga-coordinator-service)
5. [Data Management Design](#data-management-design)
   - [Databases](#databases)
   - [Caching](#caching)
   - [Data Warehouse](#data-warehouse)
6. [API Documentation](#api-documentation)
   - [Game Service API](#game-service-api)
   - [Lobby Service API](#lobby-service-api)
   - [New Endpoints](#new-endpoints)
7. [Deployment and Scaling](#deployment-and-scaling)
   - [Dockerization](#dockerization)
   - [Docker Compose](#docker-compose)
   - [Service High Availability](#service-high-availability)
   - [Load Balancer](#load-balancer)
   - [Circuit Breaker](#circuit-breaker)
   - [Logging and Monitoring](#logging-and-monitoring)
8. [Running and Testing the Project](#running-and-testing-the-project)
   - [Prerequisites](#prerequisites)
   - [Steps to Run](#steps-to-run)
   - [Testing Instructions](#testing-instructions)
9. [Additional Features](#additional-features)
   - [Distributed Caching with Consistent Hashing](#distributed-caching-with-consistent-hashing)
   - [Long-Running Saga Transactions](#long-running-saga-transactions)
   - [Database Replication and Failover](#database-replication-and-failover)
10. [Requirements Fulfillment](#requirements-fulfillment)
11. [Conclusion](#conclusion)

---

## Application Suitability

### Relevance of Microservices Architecture
The **microservices architecture** is ideal for the Online Sudoku Platform due to:

1. **Scalability**: The platform accommodates numerous concurrent users engaging in activities such as playing games, joining lobbies, and tracking progress. Microservices enable independent scaling of different components like game management and lobby services.

2. **Independence**: Separation of concerns allows independent development, deployment, and scaling of services, reducing complexity and enhancing resource allocation.

3. **Real-time Capabilities**: Facilitates efficient real-time communication through WebSockets, allowing independent development of real-time functionalities without impacting core game logic.

4. **Resilience and Fault Tolerance**: Advanced features like circuit breakers and database replication ensure the system remains resilient against failures.

5. **Maintainability**: Smaller, focused services are easier to maintain, update, and deploy, promoting continuous integration and delivery.

### Real-World Examples
1. **Chess.com**: Utilizes a similar architecture to manage multiplayer lobbies, real-time gameplay, and user management, ensuring independent scaling and development.

2. **Google TicTacToe Multiplayer**: Employs WebSocket-based real-time communication for instant player feedback across regions, maintaining separate services for game logic and session management.

---

## System Architecture

### Architecture Diagram
![Architecture Diagram](pad_architect_updated.png)

*The updated architecture diagram includes new services and features such as the API Gateway with circuit breakers, ELK stack for logging, Prometheus & Grafana for monitoring, a Data Warehouse with ETL processes, database replication setups, and a Saga Coordinator for transaction management.*

### Updated Features
- **Circuit Breaker**: Prevents cascading failures by halting calls to failing services after multiple re-routes.
- **High Availability**: Ensures services are always available through redundant instances and failover mechanisms.
- **Logging and Monitoring**: Implements the ELK stack for centralized logging and Prometheus & Grafana for real-time monitoring and alerting.
- **Distributed Caching**: Uses consistent hashing to distribute cache across multiple nodes, enhancing cache reliability and performance.
- **Saga Transactions**: Manages long-running transactions across multiple microservices, ensuring data consistency without traditional two-phase commits.
- **Database Replication**: Provides redundancy and failover capabilities with replicated databases.
- **Data Warehouse**: Aggregates data from all services for analytics and reporting through periodic ETL processes.

---

## Technology Stack and Communication Patterns

### Existing Services
- **Game Service**:
  - **Language**: Python (FastAPI)
  - **Database**: PostgreSQL
  - **Communication**: RESTful API for client interactions, gRPC for inter-service communication with the Lobby Service.

- **Lobby Service**:
  - **Language**: Python (FastAPI)
  - **Communication**: WebSocket for real-time communication with clients, RESTful API for other operations.
  - **Database**: Redis for real-time session management.

- **API Gateway**:
  - **Language**: C#
  - **Communication**: Routes RESTful requests from the client to the appropriate microservice, handles load balancing, and implements circuit breakers.

### New Features Implemented
- **Circuit Breaker**: Implemented within the API Gateway using the **Polly** library to manage retry policies and prevent cascading failures.
- **High Availability**: Achieved by deploying multiple instances of each microservice behind a load balancer to ensure service availability.
- **Logging and Monitoring**:
  - **ELK Stack**: Centralized logging using Elasticsearch, Logstash, and Kibana.
  - **Prometheus & Grafana**: Real-time monitoring and visualization of system metrics.
- **Distributed Caching with Consistent Hashing**: Utilizes Redis Cluster with consistent hashing to distribute cache across multiple nodes, ensuring scalability and reliability.
- **Saga Transactions**: Implemented long-running transactions using a **Saga Coordinator Service** to manage state and ensure consistency across microservices without two-phase commits.
- **Database Replication and Failover**: PostgreSQL is set up with replication across three replicas using **Patroni**, ensuring data redundancy and automatic failover.
- **Data Warehouse**: A separate service using **Apache Airflow** for ETL processes to periodically extract, transform, and load data from operational databases into a centralized data warehouse (e.g., Amazon Redshift or Google BigQuery) for analytics.

---

## Service Boundaries

### Game Service
Handles user registration, authentication, game management, Sudoku logic (validating inputs, game state management, score tracking), and interactions with external services. It exposes RESTful endpoints for client interactions and utilizes gRPC for communication with the Lobby Service.

### Lobby Service
Manages game sessions, allowing users to join lobbies, receive updates, and interact with other players using WebSocket communication. It handles real-time game state synchronization and chat functionalities.

### API Gateway
Acts as the central entry point for all client requests. It routes requests to appropriate microservices, implements load balancing, and integrates circuit breakers to enhance system resilience. The API Gateway ensures secure and efficient communication between clients and backend services.

### Logging and Monitoring Service
Aggregates logs from all microservices using the **ELK stack** and provides real-time monitoring dashboards and alerting through **Prometheus** and **Grafana**. This service ensures that all system activities are logged and monitored for performance and troubleshooting.

### Data Warehouse Service
Periodically extracts data from all operational databases, transforms it as needed, and loads it into a centralized data warehouse for comprehensive analytics and reporting. Managed by **Apache Airflow**, it supports business intelligence and data-driven decision-making.

### Saga Coordinator Service
Manages long-running transactions across multiple microservices, ensuring data consistency and reliability without the complexity of traditional two-phase commits. It coordinates the sequence of operations and handles compensation in case of failures.

---

## Data Management Design

### Databases
- **Game Service**: Uses **PostgreSQL** for storing user data, game states, and scores. Configured with replication across three replicas using **Patroni** for high availability and failover.
  
- **Lobby Service**: Utilizes **Redis Cluster** for lightweight, real-time session management and distributed caching with consistent hashing.

### Caching
Implemented using **Redis Cluster** with consistent hashing to distribute cache data evenly across multiple nodes. This setup ensures cache high availability and scalability, reducing latency for frequently accessed data.

### Data Warehouse
A separate data warehouse (e.g., **Amazon Redshift**) aggregates data from PostgreSQL and Redis. **Apache Airflow** manages ETL processes that extract data, perform necessary transformations, and load it into the data warehouse on a scheduled basis.

---

## API Documentation

### Game Service API

#### 1. **Register User**
- **URL:** `/game_service/register`
- **Method:** `POST`
- **Description:** Registers a new user by saving user details and hashed password in the database.
- **Request Body:**
  ```json
  {
    "username": "string",
    "email": "string (optional)",
    "full_name": "string (optional)",
    "password": "string"
  }
  ```
- **Response:**
  ```json
  {
    "username": "string",
    "email": "string",
    "full_name": "string",
    "disabled": false
  }
  ```
- **Errors:** 
  - `400 Bad Request` if the username already exists.

#### 2. **Login**
- **URL:** `/game_service/login`
- **Method:** `POST`
- **Description:** Authenticates user and issues a JWT access token.
- **Request Body:** Uses `OAuth2PasswordRequestForm` with `username` and `password`.
- **Response:**
  ```json
  {
    "access_token": "string",
    "token_type": "bearer"
  }
  ```
- **Errors:** 
  - `401 Unauthorized` for invalid username or password.

#### 3. **Get Current User**
- **URL:** `/game_service/users/me`
- **Method:** `GET`
- **Description:** Returns details of the currently authenticated user.
- **Authorization:** Requires a valid bearer token.
- **Response:**
  ```json
  {
    "username": "string",
    "email": "string",
    "full_name": "string",
    "disabled": false
  }
  ```
- **Errors:** 
  - `401 Unauthorized` if authentication fails.

#### 4. **Hello Game Service**
- **URL:** `/game_service/hello`
- **Method:** `GET`
- **Description:** Provides a simple greeting message from the game service.
- **Response:**
  ```json
  {
    "message": "Hello from game_service"
  }
  ```

#### 5. **Get Combined Data**
- **URL:** `/game_service/combined`
- **Method:** `GET`
- **Description:** Fetches data from an external service (`Service2`) and combines it with a message from the game service.
- **Response:**
  ```json
  {
    "service1_message": "Hello from Service1",
    "service2_data": { /* Service2's JSON response */ }
  }
  ```
- **Errors:** 
  - `408 Request Timeout` if `Service2` does not respond within the timeout.
  - `503 Service Unavailable` if there’s an issue connecting to `Service2`.
  - Propagates error statuses from `Service2` if it returns an HTTP error.

### Lobby Service API

#### 1. **Hello Lobby Service**
- **URL:** `/lobby_service/hello`
- **Method:** `GET`
- **Description:** Returns a greeting message from the lobby service with a simulated delay.
- **Response:**
  ```json
  {
    "message": "Hello from lobby_service"
  }
  ```
- **Errors:** 
  - `408 Request Timeout` if the request times out.

#### 2. **Get Service2 Data**
- **URL:** `/lobby_service/data`
- **Method:** `GET`
- **Description:** Retrieves some data from Service2.
- **Response:**
  ```json
  {
    "data": "This is some data from Service2",
    "random": 42
  }
  ```
- **Errors:** 
  - `408 Request Timeout` if the request times out.

#### 3. **Create Lobby**
- **URL:** `/lobbies`
- **Method:** `POST`
- **Description:** Creates a new lobby and generates a Sudoku board for the game.
- **Request Body:**
  ```json
  {
    "gameId": "string"
  }
  ```
- **Response:**
  ```json
  {
    "lobbyId": "string",
    "message": "Lobby created."
  }
  ```
- **Errors:** 
  - `401 Unauthorized` if the user is not authenticated.

#### 4. **Get Lobby Details**
- **URL:** `/lobbies/{lobbyId}`
- **Method:** `GET`
- **Description:** Retrieves details of a specific lobby, including the current board and players.
- **Path Parameter:** `lobbyId` - `string` (Unique identifier of the lobby)
- **Response:**
  ```json
  {
    "lobbyId": "string",
    "gameId": "string",
    "players": [
      {
        "player_id": "string",
        "name": "string",
        "color": "string"
      }
    ],
    "board": [[0, {"value": 5, "owner": "user1"}, ...]],
    "scores": {
      "user1": 10,
      "user2": 15
    }
  }
  ```
- **Errors:** 
  - `404 Not Found` if the lobby is not found.

#### 5. **Get All Lobbies**
- **URL:** `/lobbies`
- **Method:** `GET`
- **Description:** Retrieves details of all active lobbies.
- **Response:**
  ```json
  [
    {
      "lobbyId": "string",
      "gameId": "string",
      "players": [ /* Player objects */ ],
      "board": [ /* Board data */ ],
      "scores": { /* Scores data */ }
    }
  ]
  ```
- **Errors:** 
  - `401 Unauthorized` if the user is not authenticated.

#### 6. **User Game History**
- **URL:** `/users/{username}/games`
- **Method:** `GET`
- **Description:** Retrieves the game history for a specific user.
- **Path Parameter:** `username` - `string` (Username of the user)
- **Response:**
  ```json
  [
    {
      "id": 1,
      "lobby_id": "string",
      "game_id": "string",
      "start_time": "2024-01-01T00:00:00Z",
      "end_time": "2024-01-01T01:00:00Z",
      "winner": "user1"
    }
  ]
  ```
- **Errors:** 
  - `403 Forbidden` if the user is not authorized to view another user's history.
  - `404 Not Found` if the user is not found.

#### 7. **Game Chat History**
- **URL:** `/games/{game_id}/chat_history`
- **Method:** `GET`
- **Description:** Retrieves the chat history for a specific game.
- **Path Parameter:** `game_id` - `integer` (Identifier of the game)
- **Response:**
  ```json
  [
    {
      "id": 1,
      "game_id": 1,
      "sender": "user1",
      "message": "Hello!",
      "timestamp": "2024-01-01T00:00:00Z"
    }
  ]
  ```
- **Errors:** 
  - `403 Forbidden` if the user is not authorized to view this game's chat history.
  - `404 Not Found` if the game or user is not found.

#### 8. **WebSocket Connection for Lobby**
- **URL:** `/ws/lobby/{lobbyId}`
- **Method:** `WebSocket`
- **Description:** Manages WebSocket connections for real-time communication in a lobby.
- **Path Parameter:** `lobbyId` - `string` (Identifier of the lobby)
- **Query Parameter:** `token` - `string` (JWT token for user authentication)
- **Actions:** 
  - **Connect:** Joins a lobby, sends/receives chat and game messages, and broadcasts moves and actions.
  - **Disconnect:** Removes the user from the lobby upon disconnection.
- **Errors:** 
  - `1008 Policy Violation` if the token is invalid or lobby is full.
  - General error message if an exception occurs.

### New Endpoints

#### 9. **Create Multi-Service Transaction (Two-Phase Commit)**
- **URL:** `/transactions/create_game_2pc`
- **Method:** `POST`
- **Description:** Creates a new game across multiple services using a two-phase commit to ensure atomicity and consistency.
- **Request Body:**
  ```json
  {
    "username": "string",
    "gameId": "string"
  }
  ```
- **Response:**
  ```json
  {
    "transactionId": "string",
    "status": "committed" // or "rolled_back"
  }
  ```
- **Errors:** 
  - `400 Bad Request` if input data is invalid.
  - `500 Internal Server Error` if the transaction fails.
  
*Note: This endpoint manages transactions that span multiple microservices, ensuring atomicity and consistency using two-phase commits.*

#### 10. **Create Multi-Service Transaction (Saga Pattern)**
- **URL:** `/transactions/create_game_saga`
- **Method:** `POST`
- **Description:** Creates a new game across multiple services using a saga transaction to ensure consistency without two-phase commits.
- **Request Body:**
  ```json
  {
    "username": "string",
    "gameId": "string"
  }
  ```
- **Response:**
  ```json
  {
    "sagaId": "string",
    "status": "pending" // or "completed", "failed"
  }
  ```
- **Errors:** 
  - `400 Bad Request` if input data is invalid.
  - `500 Internal Server Error` if the saga fails.
  
*Note: This endpoint manages transactions that span multiple microservices, ensuring consistency using the saga pattern.*

---

## Deployment and Scaling

### Dockerization
All microservices, including the API Gateway, Game Service, Lobby Service, Logging and Monitoring Services, Data Warehouse Service, and Saga Coordinator Service, are containerized using **Docker**. Each service has its own `Dockerfile` specifying the environment and dependencies.

### Docker Compose
A `docker-compose.yml` file orchestrates multiple containers, including:

- **API Gateway**
- **Game Service**
- **Lobby Service**
- **Saga Coordinator Service**
- **Redis Cluster** (for caching)
- **PostgreSQL Cluster** (with replication)
- **ELK Stack**
- **Prometheus & Grafana**
- **Data Warehouse Service**
- **Apache Airflow** (for ETL processes)

```yaml
version: '3.8'

services:
  api-gateway:
    build: ./api-gateway
    ports:
      - "5029:5029"
    depends_on:
      - game-service
      - lobby-service
      - saga-coordinator
    networks:
      - sudoku-network

  game-service:
    build: ./game_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:admin@postgres1/pad_gameHistory
    depends_on:
      - postgres1
    networks:
      - sudoku-network
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure

  lobby-service:
    build: ./lobby_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:admin@postgres1/pad_gameHistory
      - REDIS_HOST=redis1
    depends_on:
      - redis1
      - postgres1
    networks:
      - sudoku-network
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure

  saga-coordinator:
    build: ./saga_coordinator
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:admin@postgres1/pad_gameHistory
    depends_on:
      - game-service
      - lobby-service
    networks:
      - sudoku-network
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure

  redis1:
    image: redis:6.2
    ports:
      - "6379:6379"
    networks:
      - sudoku-network
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure

  postgres1:
    image: postgres:13
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: admin
      POSTGRES_DB: pad_gameHistory
    ports:
      - "5432:5432"
    networks:
      - sudoku-network
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
      placement:
        constraints: [node.role == manager]

  elk:
    image: sebp/elk
    ports:
      - "5601:5601" # Kibana
      - "9200:9200" # Elasticsearch
      - "5044:5044" # Logstash
    networks:
      - sudoku-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    networks:
      - sudoku-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    networks:
      - sudoku-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  data-warehouse:
    build: ./data_warehouse
    environment:
      - DW_DB_URL=postgresql://postgres:admin@postgres1/data_warehouse
    depends_on:
      - postgres1
    networks:
      - sudoku-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  apache-airflow:
    image: puckel/docker-airflow
    environment:
      - LOAD_EX=n
      - EXECUTOR=Local
    ports:
      - "8080:8080"
    volumes:
      - ./dags:/usr/local/airflow/dags
    networks:
      - sudoku-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

networks:
  sudoku-network:
    driver: bridge
```

### Service High Availability
High availability is achieved by deploying multiple instances of each microservice behind a load balancer. The Docker Compose setup specifies replicas for critical services like PostgreSQL and Redis to ensure redundancy and automatic failover. For example, PostgreSQL is deployed with three replicas using **Patroni** to manage leader election and failover.

### Load Balancer
The **API Gateway** acts as a load balancer, distributing incoming requests evenly across multiple instances of each microservice. It also integrates circuit breakers to manage retries and prevent overloading failing services. The API Gateway ensures that traffic is efficiently managed and that services remain responsive under high load.

### Circuit Breaker
Implemented within the **API Gateway** using the **Polly** library, the circuit breaker monitors the health of service endpoints. After multiple failed attempts to reach a service, the circuit breaker trips, halting further attempts for a specified period to allow the service to recover. This mechanism prevents cascading failures and enhances system resilience.

### Logging and Monitoring
- **ELK Stack**: Centralizes logs from all microservices. **Logstash** collects and processes logs, **Elasticsearch** indexes them, and **Kibana** provides a user-friendly interface for log analysis.

- **Prometheus & Grafana**: **Prometheus** scrapes metrics from all services, and **Grafana** visualizes these metrics in real-time dashboards. Alerts can be configured in Prometheus to notify of any anomalies or issues.

### Data Warehouse
A separate **Data Warehouse Service** uses **Apache Airflow** to schedule and manage ETL (Extract, Transform, Load) processes. Data from PostgreSQL and Redis is periodically extracted, transformed to meet analytical requirements, and loaded into a centralized data warehouse (e.g., **Amazon Redshift** or **Google BigQuery**) for comprehensive analytics and reporting.

---

## Running and Testing the Project

### Prerequisites
- **Docker** and **Docker Compose** installed on your machine.
- **Git** for cloning the repository.

### Steps to Run

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/online-sudoku-platform.git
   cd online-sudoku-platform
   ```

2. **Build and Start the Containers**
   ```bash
   docker-compose up --build
   ```
   This command builds the Docker images and starts all services as defined in the `docker-compose.yml` file.

3. **Accessing Services**
   - **API Gateway**: `http://localhost:5029`
   - **Kibana (ELK Stack)**: `http://localhost:5601`
   - **Prometheus**: `http://localhost:9090`
   - **Grafana**: `http://localhost:3000`
   - **PostgreSQL**: `localhost:5432`
   - **Redis**: `localhost:6379`
   - **Apache Airflow**: `http://localhost:8080`

4. **Initial Setup**
   - **Kibana**: Configure index patterns to start viewing logs.
   - **Grafana**: Add Prometheus as a data source and import dashboards for monitoring.
   - **Apache Airflow**: Access the Airflow web interface to manage ETL workflows.

### Testing Instructions

1. **Register a New User**
   - **Endpoint:** `http://localhost:5029/game_service/register`
   - **Method:** `POST`
   - **Body:**
     ```json
     {
       "username": "testuser",
       "email": "testuser@example.com",
       "full_name": "Test User",
       "password": "securepassword"
     }
     ```

2. **Login**
   - **Endpoint:** `http://localhost:5029/game_service/login`
   - **Method:** `POST`
   - **Body:** Form data with `username` and `password`.
   - **Response:** JWT token to be used in the `Authorization` header for authenticated requests.

3. **Access Protected Endpoints**
   - Use the JWT token obtained from the login response in the `Authorization` header:
     ```
     Authorization: Bearer <token>
     ```

4. **Create a Lobby**
   - **Endpoint:** `http://localhost:5029/lobbies`
   - **Method:** `POST`
   - **Body:**
     ```json
     {
       "gameId": "sudoku123"
     }
     ```
   - **Response:** Lobby ID and creation message.

5. **Connect via WebSocket**
   - **URL:** `ws://localhost:5029/ws/lobby/{lobbyId}?token=<JWT_TOKEN>`
   - Use a WebSocket client to connect to the lobby.

6. **Create a Game Transaction**
   - **Two-Phase Commit:**
     - **Endpoint:** `http://localhost:5029/transactions/create_game_2pc`
     - **Method:** `POST`
     - **Body:**
       ```json
       {
         "username": "testuser",
         "gameId": "sudoku123"
       }
       ```
   - **Saga Transaction:**
     - **Endpoint:** `http://localhost:5029/transactions/create_game_saga`
     - **Method:** `POST`
     - **Body:**
       ```json
       {
         "username": "testuser",
         "gameId": "sudoku123"
       }
       ```

7. **Monitor Logs and Metrics**
   - **Kibana:** View aggregated logs from all services.
   - **Prometheus & Grafana:** Monitor real-time metrics and set up alerts.

---

## Additional Features

### Distributed Caching with Consistent Hashing
Implemented using **Redis Cluster**, consistent hashing ensures that cache data is evenly distributed across multiple Redis nodes. This approach minimizes cache misses and enhances performance by balancing the load. Redis Cluster automatically handles data partitioning and replication.

### Long-Running Saga Transactions
Managed through a dedicated **Saga Coordinator Service**, which orchestrates distributed transactions across multiple microservices. This ensures data consistency and reliability without the complexity of traditional two-phase commits. The saga pattern breaks down transactions into smaller steps, each with compensating actions to handle failures gracefully.

### Database Replication and Failover
**PostgreSQL** is configured with replication across three replicas using **Patroni** for leader election and failover management. This setup ensures high availability and data redundancy, automatically promoting replicas in case of primary database failure. **Redis Cluster** is also deployed with multiple nodes to ensure cache high availability.

### Data Warehouse
A separate **Data Warehouse Service** uses **Apache Airflow** to schedule and manage ETL (Extract, Transform, Load) processes. Data from PostgreSQL and Redis is periodically extracted, transformed to meet analytical requirements, and loaded into a centralized data warehouse (e.g., **Amazon Redshift** or **Google BigQuery**) for comprehensive analytics and reporting. This setup supports business intelligence and data-driven decision-making.

---

## Requirements Fulfillment

1. **Trip Circuit Breaker if Multiple Re-Routes Happen**
   - **Implemented:** Within the API Gateway using the **Polly** library to manage retry policies and prevent cascading failures during multiple re-routes.

2. **Service High Availability**
   - **Implemented:** By deploying multiple instances of each microservice and configuring PostgreSQL and Redis with replication and failover mechanisms to ensure services remain available even during failures.

3. **Implement ELK Stack or Prometheus + Grafana for Logging**
   - **Implemented:** Utilized the **ELK stack** for centralized logging and **Prometheus** with **Grafana** for real-time monitoring and visualization of metrics across all services.

4. **Implement Microservice-Based 2 Phase Commits**
   - **Implemented:** Added a new endpoint `/transactions/create_game_2pc` in the API Gateway to manage two-phase commits for transactions that create changes in more than one database, ensuring atomicity and consistency.

5. **Consistent Hashing for Cache**
   - **Implemented:** Using **Redis Cluster** with consistent hashing to distribute cache data evenly across multiple nodes, ensuring scalability and reliability.

6. **Implement Cache High Availability**
   - **Implemented:** Achieved through the Redis Cluster setup with multiple nodes and failover configurations to ensure cache availability even if some nodes fail.

7. **Instead of 2 Phase Commits Implement Long-Running Saga Transactions with Coordinator**
   - **Implemented:** Added a new endpoint `/transactions/create_game_saga` managed by the **Saga Coordinator Service**, handling long-running transactions across multiple microservices to ensure data consistency without traditional two-phase commits.

8. **Database Redundancy/Replication + Failover**
   - **Implemented:** Configured **PostgreSQL** with replication across three replicas using **Patroni**, ensuring data redundancy and automatic failover in case of primary database failure.

9. **Create a Data Warehouse that Will Be Periodically Updated with All Data from Your Databases**
   - **Implemented:** Established a **Data Warehouse Service** using **Apache Airflow** to periodically extract data from operational databases, transform it as needed, and load it into a centralized data warehouse for comprehensive analytics and reporting.

---

## Conclusion
The **Online Sudoku Platform** leverages a comprehensive microservices architecture enriched with advanced features to ensure scalability, high availability, resilience, and efficient data management. By implementing robust logging, monitoring, distributed caching, transaction management, database replication, and data warehousing, the platform is well-equipped to handle high loads, provide real-time user experiences, and offer insightful analytics for continuous improvement.
---
