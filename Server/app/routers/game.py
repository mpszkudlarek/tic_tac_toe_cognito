import cognitojwt
import os
import uuid
import logging

from boto3 import resource

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.TicTacToe import TicTacToe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game", responses={404: {"description": "Not found"}})

games = {}

REGION = 'us-east-1'  # North Virginia
USERPOOL_ID = 'us-east-1_Lm3EUTsrB'  # User pool from Cognito UI
APP_CLIENT_ID = '4atad40os2e7ld1h6dmscm2n3u'  # App client id from Cognito UI

# Below are the temporary credentials from AWS 
os.environ[
    'AWS_SESSION_TOKEN'] = 'IQoJb3JpZ2luX2VjEPD//////////wEaCXVzLXdlc3QtMiJGMEQCIHty8aPUwAFj9WD/xhbYW9mUes5yDcueXHyuqb/YDomiAiA6PgX6BgVg/gC2Nv0FxsXZAVH7myYkdhY+IU7VuQIUiiqsAgh5EAAaDDA3NzEzNzc1ODkwNiIMkEXRSRxcGnwJ1kTnKokCYWonqMYmrejE44wqdLbmE5s/N8qDeRfLkDp1uZ1WGEqf2RdNGbCUuWKMM3+5hFaFahDMDJSPLEim9ai0Oh3LGV1DfMZWBymT/+3uZKejmKnBSiqUQPyDaCm26bR0eolxiU6eDHHzScl2U2/vqquoYE7PdY7Pruld5oFfXjUFrDX0/jwbC9COw/SD3PQz+bLFdrY2rMjmpdbakPlrCwXmE++tN0DyIP4Hr2/AJ5e7uhw7hMrxD+NOxopq8cVCpThcfAzGQZ42fZw8d7iYavlOnobR834e/sJ73vzsbqEJsasKXoiQsmz5lnS3THIMrgyRU+PB8N6L2TwJeRWreVrsDUPQocFG1tIIZDCArPKyBjqeAY5Oc6+japEPIdkkZ4JW2amKkcBo92ISr0jHez0wY2FUBnixsBP7wxMyjBn6HBzvkSPSEpTHRpmu7pcaqPFjS6C6UuSbXRWkVkPLQ/uxhBSnazb7TN9tWUzZRud3Z483GybWVHsAoeVysPY4yrqJwQFqtq6QlNp37MQC913/DnKT/uaEwi+9SFB8G46eaMqnZnlhY339kPr0/tKkk4Je'
os.environ['AWS_ACCESS_KEY_ID'] = 'ASIARD5OEZK5HDBOJP7J'
os.environ['AWS_SECRET_ACCESS_KEY'] = '8ToPwHvsAnXvv3XsowAuz0KWQIIBLjVNRoo2rKvY'
os.environ['AWS_DEFAULT_REGION'] = REGION


def authorize(token):
    try:
        logger.info(f"Token: {token}")
        verified = cognitojwt.decode(token, REGION, USERPOOL_ID, app_client_id=APP_CLIENT_ID)
        return verified
    except Exception as e:
        logger.info(f"Exception: {e}")
        return {}


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, WebSocket] = {}
        self.waiting_connection: WebSocket = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        token = await websocket.receive_text()
        auth_dict = authorize(token)

        if len(auth_dict) == 0:
            await websocket.send_json({"board": "", "message": "You are not authorized", "opponent": ""})
            await websocket.close()
            raise Exception

        if self.waiting_connection is not None:
            # Pair the waiting connection with the new connection
            await self.pair_waiting(websocket)
        else:
            self.waiting_connection = websocket

    async def disconnect(self, websocket: WebSocket):
        if websocket.client_id in self.active_connections:
            partner = self.active_connections[self.active_connections[websocket.client_id].partner_id]
            # Pair the waiting connection with the new connection
            if self.waiting_connection is not None:
                await self.pair_waiting(partner)
            else:
                self.waiting_connection = partner
                del self.active_connections[self.active_connections[websocket.client_id].partner_id]
            del self.active_connections[websocket.client_id]
        if self.waiting_connection == websocket:
            self.waiting_connection = None

    async def send_group_message(self, message: str, sender_id: int):
        # Send message to both partners in the group
        if sender_id in self.active_connections:
            partner_id = self.active_connections[sender_id].partner_id
            await self.active_connections[sender_id].send_text(message)
            await self.active_connections[partner_id].send_text(message)
        else:
            await self.waiting_connection.send_text(message)

    async def pair_waiting(self, user: WebSocket):
        # Assign partner id
        user.partner_id = self.waiting_connection.client_id
        self.waiting_connection.partner_id = user.client_id
        # Add connections to dict
        self.active_connections[user.client_id] = user
        self.active_connections[self.waiting_connection.client_id] = self.waiting_connection

        # Create game
        games[user.client_id] = TicTacToe()
        self.active_connections[user.client_id].game_id = user.client_id
        self.active_connections[user.client_id].player = 'O'
        self.active_connections[self.waiting_connection.client_id].game_id = user.client_id
        self.active_connections[self.waiting_connection.client_id].player = 'X'
        print(games)
        await self.waiting_connection.send_json({"board": [[' ' for _ in range(3)] for _ in range(3)], "message": "Opponent found, your turn.", "opponent": user.username})
        # await self.waiting_connection.send_text(f"{user.client_id} has joined.")
        self.waiting_connection = None

    async def end_game(
            self, user: WebSocket, user_message, partner_message, client_id: int, game: TicTacToe,
            game_id: int):

        await user.send_json({"board": game.board, "message": user_message, "opponent": manager.active_connections[manager.active_connections[client_id].partner_id].username})
        await manager.active_connections[manager.active_connections[client_id].partner_id].send_json({"board": game.board, "message": partner_message, "opponent": user.username})
        await manager.active_connections[manager.active_connections[client_id].partner_id].close()
        del manager.active_connections[manager.active_connections[client_id].partner_id]
        del manager.active_connections[client_id]
        del games[game_id]


manager = ConnectionManager()


def save_result(player1: str, player2: str, winner: str):
    results_table = resource("dynamodb").Table("bazattt")
    results_table.put_item(
        Item={
            "game_id": uuid.uuid4().hex,
            "player_1": player1,
            "player_2": player2,
            "winner": winner
        }
    )


@router.websocket("/ws/{client_id}/{username}")
async def websocket_endpoint(websocket: WebSocket, client_id: int, username: str):
    # await websocket.accept()
    websocket.client_id = client_id  # Assign a client ID to the websocket
    websocket.username = username
    try:
        await manager.connect(websocket)
    except:
        return
    # if (manager.waiting_connection != websocket):
    try:
        if manager.waiting_connection != websocket:
            await websocket.send_json({"board": [[' ' for _ in range(3)] for _ in range(3)], "message": "Waiting for opponent's move...",
                                       "opponent": manager.active_connections[manager.active_connections[client_id].partner_id].username})
        while True:
            data = await websocket.receive_text()
            row, col = map(int, data.split())
            if manager.waiting_connection != websocket:
                game_id = manager.active_connections[websocket.client_id].game_id
                print(game_id)
                game = games[game_id]

                if (game.current_player == websocket.player):
                    if game.make_move(row, col):
                        if game.check_winner():
                            # TODO: tutaj zakomentowane byklo na dole
                            save_result(username, manager.active_connections[manager.active_connections[client_id].partner_id].username, username)
                            await manager.end_game(websocket, "You win!!!", "You lose.", client_id, game, game_id)
                            break
                        if game.check_draw():
                            # TODO: tutaj bylo zakomentowane
                            save_result(username, manager.active_connections[manager.active_connections[client_id].partner_id].username, "draw")
                            await manager.end_game(websocket, "Draw!!!", "Draw!!!", client_id, game, game_id)
                            break
                        await websocket.send_json({"board": game.board, "message": "Waiting for opponent's move...",
                                                   "opponent": manager.active_connections[manager.active_connections[client_id].partner_id].username})
                        await manager.active_connections[manager.active_connections[client_id].partner_id].send_json(
                            {"board": game.board, "message": "Your turn.", "opponent": websocket.username})
                print(data)
        await websocket.close()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)