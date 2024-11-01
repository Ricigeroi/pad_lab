
# Online Sudoku Platform

## Project Description
An online Sudoku platform where users can play Sudoku games, track their progress, and participate in lobbies for game sessions. The platform uses a microservice architecture, ensuring scalability and separation of concerns. The two main microservices focus on user/game management and game lobby management through WebSocket communication.

## Application Suitability

### Relevance of Microservices Architecture
Microservices architecture is suitable for the Online Sudoku Platform because:

1. **Scalability**: The platform needs to handle multiple users simultaneously playing games, joining lobbies, or tracking progress. Microservices allow independent scaling of game and lobby services.
   
2. **Independence**: By separating concerns, the lobby and game management systems can be developed, deployed, and scaled independently. This approach reduces complexity and allows for better resource allocation.

3. **Real-time Capabilities**: The lobby service requires real-time communication between players, which can be efficiently handled using WebSockets. This separation enables independent development of WebSocket functionality without affecting the game logic.

### Real-World Examples
1. **Chess.com**: Chess.com employs a similar architecture to handle multiplayer lobbies, real-time gameplay, and user management. Each service handles specific tasks, allowing for independent development and scaling during peak usage.
   
2. **TicTacToe Multiplayer (Google)**: Google uses WebSocket-based real-time communication for multiplayer games, providing instant feedback to players across different regions while maintaining separate services for game logic and session management.

## Service Boundaries
The platform is divided into two core microservices:

1. **Game Service**: Handles user registration, game management, and Sudoku logic (validating inputs, game state management, score tracking).
   
2. **Lobby Service**: Manages game sessions, allowing users to join lobbies, receive updates, and interact with other players using WebSocket communication.

### System Architecture Diagram
The architecture would consist of the following elements:

- **API Gateway** (written in C#): Central entry point for all requests, routing them to the appropriate microservice.
- **Load Balancer**: Distributes incoming requests across multiple instances of each microservice for better availability.
- **Game Service** (Python with FastAPI): Handles user and game management. Exposes RESTful endpoints for user authentication, game state, and score tracking.
- **Lobby Service** (Python with FastAPI and WebSocket): Manages game sessions, enabling real-time communication via WebSocket.
- **Database**: Each microservice has its own database to avoid cross-service data dependencies. Game Service uses PostgreSQL, and Lobby Service uses Redis for session management.
  
![alt-text](pad_architect.png)

## Technology Stack and Communication Patterns
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
  - **Communication**: Routes RESTful requests from the client to the appropriate microservice, handles load balancing.

### Communication Patterns
1. **RESTful API (Game Service)**: Standard HTTP requests for user management and game state.
2. **WebSocket (Lobby Service)**: Handles real-time communication between users in game lobbies.
3. **gRPC**: Used for inter-service communication between the Game and Lobby services, ensuring high performance and low-latency communication for game session management.

## Data Management Design
Each microservice will maintain its own database, ensuring separation of concerns. The Game Service uses PostgreSQL, while the Lobby Service uses Redis for lightweight, real-time session data storage.

### Endpoints
# Game Service API Documentation

## Overview
This API provides endpoints for user registration, authentication, retrieving user information, and interaction with an external service (`Service2`). It uses JWT for authentication and secure access.

# Endpoints

## Game Service API Documentation

### 1. **Register User**
   - **URL:** `/game_service/register`
   - **Method:** `POST`
   - **Description:** Registers a new user by saving user details and hashed password in the database.
   - **Request Body:**
     - `username`: `str` - Unique username
     - `email`: `Optional[str]` - User's email (optional)
     - `full_name`: `Optional[str]` - User's full name (optional)
     - `password`: `str` - User's password
   - **Response:** Returns user details upon successful registration.
   - **Errors:** 400 if the username already exists.

### 2. **Login**
   - **URL:** `/game_service/login`
   - **Method:** `POST`
   - **Description:** Authenticates user and issues a JWT access token.
   - **Request Body:** Uses `OAuth2PasswordRequestForm` (username and password).
   - **Response:** 
     - `access_token`: `str` - JWT token for authenticated requests
     - `token_type`: `str` - Type of token, e.g., "bearer"
   - **Errors:** 401 for invalid username or password.

### 3. **Get Current User**
   - **URL:** `/game_service/users/me`
   - **Method:** `GET`
   - **Description:** Returns details of the currently authenticated user.
   - **Authorization:** Requires a valid bearer token.
   - **Response:** User details such as username, email, full name, and status.
   - **Errors:** 401 if authentication fails.

### 4. **Hello Game Service**
   - **URL:** `/game_service/hello`
   - **Method:** `GET`
   - **Description:** Provides a simple greeting message from the game service.
   - **Response:** JSON with the message `"Hello from game_service"`.

### 5. **Get Combined Data**
   - **URL:** `/game_service/combined`
   - **Method:** `GET`
   - **Description:** Fetches data from an external service (`Service2`) and combines it with a message from the game service.
   - **Response:** 
     - `service1_message`: `"Hello from Service1"`
     - `service2_data`: JSON response from `Service2`
   - **Errors:** 
     - 408 if `Service2` does not respond within the timeout.
     - 503 if there’s an issue connecting to `Service2`.
     - Error response status if `Service2` returns an HTTP error.

## JWT Configuration
For accessing protected endpoints, use the token obtained from the login endpoint as a bearer token in the authorization header (`Authorization: Bearer <token>`).



## Lobby Service API Documentation


### 1. **Hello Lobby Service**
   - **URL:** `/lobby_service/hello`
   - **Method:** `GET`
   - **Description:** Returns a greeting message from the lobby service with a simulated delay.
   - **Response:** `{ "message": "Hello from lobby_service" }`
   - **Errors:** 408 if the request times out.

### 2. **Get Service2 Data**
   - **URL:** `/lobby_service/data`
   - **Method:** `GET`
   - **Description:** Retrieves some data from Service2.
   - **Response:** 
     - `data`: Some string data from Service2.
     - `random`: Random integer for illustrative purposes.
   - **Errors:** 408 if the request times out.

### 3. **Create Lobby**
   - **URL:** `/lobbies`
   - **Method:** `POST`
   - **Description:** Creates a new lobby and generates a Sudoku board for the game.
   - **Request Body:** 
     - `gameId`: `str` - ID of the game.
   - **Response:** 
     - `lobbyId`: Unique identifier for the lobby.
     - `message`: `"Lobby created."`
   - **Errors:** None specified.

### 4. **Get Lobby Details**
   - **URL:** `/lobbies/{lobbyId}`
   - **Method:** `GET`
   - **Description:** Retrieves details of a specific lobby, including the current board and players.
   - **Path Parameter:** `lobbyId`: `str` - Unique identifier of the lobby.
   - **Response:** 
     - `lobbyId`, `gameId`, `players`, `board`, `scores` - Detailed information about the lobby.
   - **Errors:** 404 if the lobby is not found.

### 5. **Get All Lobbies**
   - **URL:** `/lobbies`
   - **Method:** `GET`
   - **Description:** Retrieves details of all active lobbies.
   - **Response:** List of lobbies with details such as `lobbyId`, `gameId`, `players`, `board`, and `scores`.
   - **Errors:** None specified.

### 6. **User Game History**
   - **URL:** `/users/{username}/games`
   - **Method:** `GET`
   - **Description:** Retrieves the game history for a specific user.
   - **Path Parameter:** `username`: `str` - Username of the user.
   - **Response:** List of game results with details like `id`, `lobby_id`, `game_id`, `start_time`, `end_time`, and `winner`.
   - **Errors:** 
     - 403 if the user is not authorized to view another user's history.
     - 404 if the user is not found.

### 7. **Game Chat History**
   - **URL:** `/games/{game_id}/chat_history`
   - **Method:** `GET`
   - **Description:** Retrieves the chat history for a specific game.
   - **Path Parameter:** `game_id`: `int` - Identifier of the game.
   - **Response:** List of chat messages with details like `id`, `game_id`, `sender`, `message`, and `timestamp`.
   - **Errors:** 
     - 403 if the user is not authorized to view this game's chat history.
     - 404 if the game or user is not found.

### 8. **WebSocket Connection for Lobby**
   - **URL:** `/ws/lobby/{lobbyId}`
   - **Method:** `WebSocket`
   - **Description:** Manages WebSocket connections for real-time communication in a lobby.
   - **Path Parameter:** `lobbyId`: `str` - Identifier of the lobby.
   - **Query Parameter:** `token`: JWT token for user authentication.
   - **Actions:** 
     - **Connect:** Joins a lobby, sends/receives chat and game messages, and broadcasts moves and actions.
     - **Disconnect:** Removes the user from the lobby upon disconnection.
   - **Errors:** 
     - 1008 if the token is invalid or lobby is full.
     - General error message if an exception occurs.

## JWT Configuration
All protected endpoints require a valid JWT access token in the authorization header: `Authorization: Bearer <token>`.


  - **Dynamic WebSocket /ws/lobby/{lobbyId}**: WebSocket endpoint for real-time communication. Each lobby will have a dynamic WebSocket route based on the `lobbyId`. The current game board will also be synchronized across all clients.
    - Push messages:
      - When a new user joins or a move is made, the updated board and lobby state will be broadcasted to all connected clients in real-time.



## Deployment and Scaling
Both microservices will be containerized using **Docker**. The platform will use **Docker Compose** to orchestrate multiple containers (Game Service, Lobby Service, Redis, PostgreSQL, and API Gateway).

### Horizontal Scaling
To handle increased load, we can deploy additional instances of the Game and Lobby services. This will be managed through the **Load Balancer** in front of the API Gateway.

- **Docker Compose** will handle service orchestration, ensuring each container is part of a shared network.
  
### Scaling WebSocket Connections
WebSocket-based services (like the Lobby Service) will be scaled by increasing the number of WebSocket instances, using Redis to handle session persistence.

### Load Balancer
The **Load Balancer** will be written in C# and integrated into the API Gateway. It will distribute incoming requests evenly across multiple instances of each microservice, ensuring high availability.
