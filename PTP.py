import hashlib
import json
from threading import Thread
from time import time, sleep
from typing import List, Optional

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

port = 5001
ip = '192.168.0.127'
initial_peer = (ip, port)
node_id = 'Node1'


class Transaction:
    def __init__(self, node_id: str, generic_data: str, timestamp=None):
        self.node_id = node_id
        self.timestamp = timestamp if timestamp is not None else time()
        self.generic_data = generic_data


class Block:
    def __init__(self, index: int, timestamp: Optional[float], transactions: List[Transaction],
                 previous_hash: str):
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.current_hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        first_transaction_data = {}

        if self.transactions:
            # If there are transactions, use data from the first one
            first_transaction = self.transactions[0]
            first_transaction_data = first_transaction.__dict__

        block_data = {
            "index": self.index,
            "timestamp": round(self.timestamp, 6),
            "transactions": [first_transaction_data],  # Include only the first transaction
            "previous_hash": self.previous_hash
        }

        block_string = json.dumps(block_data, sort_keys=True, default=str)
        calculated_hash = hashlib.sha256(block_string.encode()).hexdigest()

        print(f"Calculated hash: {calculated_hash}")
        return calculated_hash


class Blockchain:
    def __init__(self, node_id, initial_peer):
        self.node_id = node_id
        self.peer_list = [initial_peer]  # List to store connected nodes
        self.chain = [self.create_genesis_block()]
        self.transactions = []

        # Start the heartbeat thread
        self.heartbeat_thread = Thread(target=self.send_heartbeat)
        self.heartbeat_thread.daemon = True  # Terminate thread when main program ends
        self.heartbeat_thread.start()


        self.state = "PRE_PREPARED"
        self.prepare_messages = []
        self.commit_messages = []
        self.block_is_valid = False


    def send_prepare_message(self):
        self.commit_messages = []
        self.prepare_messages = []

        # Example: Broadcasting a prepare message to all nodes in the network
        for peer in self.peer_list:
            try:
                data = {
                    "peer": f"{ip}:{port}",
                    "state": "PREPARE"
                }
                response = requests.post(f'http://{peer[0]}:{peer[1]}/prepare', json=data)
                if response.status_code == 200:
                    print(f"Prepare message sent to {peer}")
                else:
                    print(f"Failed to send prepare message to {peer} with status code {response.status_code}")
            except Exception as e:
                print(f"Error sending prepare message to {peer}: {e}")
        self.state = "COMMITED"
        self.wait_for_prepare_messages(1, 0.5)


    def wait_for_prepare_messages(self, threshold=1, interval=0.5):
        # bool for number of correct messages
        condition = False
        while True:
            if len(self.prepare_messages) >= threshold:
                condition = True
                break
            time.sleep(interval)
        if condition:
            self.send_commit_message()
        else:
            self.state = "PRE_PREPARED"

    def send_commit_message(self):
        # Example: Broadcasting a prepare message to all nodes in the network
        for peer in self.peer_list:
            try:
                data = {
                    "peer": f"{ip}:{port}",
                    "state": "COMMIT"
                }
                response = requests.post(f'http://{peer[0]}:{peer[1]}/commit', json=data)
                if response.status_code == 200:
                    print(f"Prepare message sent to {peer}")
                else:
                    print(f"Failed to send prepare message to {peer} with status code {response.status_code}")
            except Exception as e:
                print(f"Error sending prepare message to {peer}: {e}")
        self.state = "INSERTED"
        self.wait_for_commit_messages(1, 0.5)

    def wait_for_commit_messages(self, threshold=1, interval=0.5):
        # bool for number of correct messages
        condition = False
        while True:
            if len(self.commit_messages) >= threshold:
                condition = True
                break
            time.sleep(interval)
        if condition:
            self.block_is_valid = True
            self.state = "PRE_PREPARED"
        else:
            self.state = "PRE_PREPARED"
            return False

    def save_chain_to_file(self, filename):
        try:
            with open(filename, 'w') as file:
                for block in self.chain:
                    block_data = {
                        "Index": block.index,
                        "Timestamp": block.timestamp,
                        "Previous Hash": block.previous_hash,
                        "Current Hash": block.current_hash,
                        "Transactions": [vars(txn) for txn in block.transactions]
                    }
                    file.write(json.dumps(block_data) + '\n')
            print(f"Blockchain data saved to file: {filename}")
        except Exception as e:
            print(f"Error saving blockchain data to file: {e}")

    def create_genesis_block(self) -> Block:
        # The genesis block has no transactions
        return Block(index=0, timestamp=0, transactions=[], previous_hash="0")

    def add_transaction(self, transaction: Transaction):
        current_block = self.chain[-1]

        # Check if the current block is full or is the genesis block
        if len(current_block.transactions) >= 5 or current_block.previous_hash == '0':
            # Create a new block with the current transactions
            self.add_block([transaction])

        else:
            # Check if the time difference is greater than 1.5 seconds
            if current_block.transactions:
                last_transaction = current_block.transactions[-1]
                time_difference = transaction.timestamp - last_transaction.timestamp

                if time_difference > 1.5:
                    current_block.transactions.append(transaction)
                    self.broadcast_transaction(transaction)

                    # Check if the block is now full and share it with other nodes
                    if len(current_block.transactions) == 5:
                        self.share_block_with_peers(current_block)
                else:
                    print("Invalid Transaction: Time difference is less than 1.5 seconds.")
            else:
                current_block.transactions.append(transaction)
                self.broadcast_transaction(transaction)

    def broadcast_transaction(self, transaction: Transaction):
        for peer in self.peer_list:
            self.send_transaction(peer, transaction)

    def add_peer(self, peer):
        # Add a new peer to the peer_list
        if peer not in self.peer_list:
            self.peer_list.append(peer)

    def remove_peer(self, peer):
        # Remove the specified peer from the peer_list
        if peer in self.peer_list:
            self.peer_list.remove(peer)
            print(f"Removed peer: {peer}")

    def send_transaction(self, peer, transaction: Transaction):
        message = {'transaction': vars(transaction)}
        # Use Flask's test client to simulate an HTTP request
        with app.test_client() as client:
            client.post(f'http://{peer[0]}:{peer[1]}/transaction', json=message)

    def add_block(self, transactions: List[Transaction]) -> Block:
        sleep(1)
        previous_block = self.chain[-1]
        new_block = Block(index=len(self.chain), timestamp=time(), transactions=transactions,
                          previous_hash=previous_block.current_hash)
        self.chain.append(new_block)
        return new_block  # Return the newly created block

    def display_chain(self):
        block_data = []  # Initialize block_data before the loop
        for block in self.chain:
            block_data.append({
                "Index": block.index,
                "Timestamp": block.timestamp,
                "Previous Hash": block.previous_hash,
                "Current Hash": block.current_hash,
                "Transactions": [vars(txn) for txn in block.transactions]
            })

        # Display connected peers
        peers_data = [{'ip': peer[0], 'port': peer[1]} for peer in self.peer_list]

        return {
            "chain": block_data,
            "peers": peers_data
        }

    def share_block_with_peers(self, block):
        for peer in self.peer_list:
            self.send_block(block)

    def send_block(self, block):
        block_data = {
            "index": block.index,
            "timestamp": block.timestamp,
            "transactions": [vars(txn) for txn in block.transactions],
            "previous_hash": block.previous_hash
        }

        message = {'block': block_data}

        for peer in self.peer_list:
            address = f"http://{peer[0]}:{peer[1]}/receive_block"
            response = requests.post(address, json=message)

            # Check the response
            if response.status_code == 200:
                print(f"Request to {address} successful")
                print(response.json())  # Print the response data if it's JSON
            else:
                print(f"Request to {address} failed with status code {response.status_code}")
                print(response.text)  # Print the response content

    def ping_peer(self, peer):
        try:
            response = requests.get(f'http://{peer[0]}:{peer[1]}/ping')
            if response.status_code == 200:
                print(f"Heartbeat to {peer} successful")
                return True
        except Exception as e:
            print(f"Failed to send heartbeat to {peer}: {e}")
        return False

    def send_heartbeat(self):
        while True:
            print("Sending heartbeat to peers...")
            for peer in self.peer_list:
                if not self.ping_peer(peer):
                    print(f"Removing {peer} from peer list due to heartbeat failure")
                    self.peer_list.remove(peer)  # Remove the peer from the list
            sleep(10)  # Send heartbeat every 10 seconds

    def register_node_globally(self, ip, port):
        data = {"ip": ip, "port": port}

        addresses = [f"http://{ip}:5002/register_node", f"http://{ip}:5003/register_node",
                     f"http://{ip}:5004/register_node"]

        for address in addresses:
            response = requests.post(address, json=data)

            # Check the response
            if response.status_code == 200:
                print(f"Request to {address} successful")
                print(response.json())  # Print the response data if it's JSON
            else:
                print(f"Request to {address} failed with status code {response.status_code}")
                print(response.text)  # Print the response content


# Instantiate the blockchain globally
blockchain = Blockchain(node_id=node_id, initial_peer=initial_peer)


# Flask route for receiving transactions
@app.route('/transaction', methods=['POST'])
def receive_transaction():
    try:
        data = request.get_json()
        transaction_data = data.get('transaction', {})

        required_fields = ['node_id', 'generic_data']
        if any(field not in transaction_data for field in required_fields):
            return jsonify({"error": "Invalid transaction data format"}), 400

        node_id_new = transaction_data['node_id']
        generic_data_new = transaction_data['generic_data']
        # Create a Transaction object from the JSON data
        transaction_new = Transaction(node_id=node_id_new, generic_data=generic_data_new)
        blockchain.add_transaction(transaction_new)

        # Add the sender as a new peer
        sender_peer = (request.remote_addr, request.environ['REMOTE_PORT'])
        blockchain.add_peer(sender_peer)

        print(f"Received Transaction: {data['transaction']}")
        return jsonify({"status": "Transaction received"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Flask route for displaying the chain
@app.route('/display_chain', methods=['GET'])
def display_chain():
    blockchain_data = blockchain.display_chain()
    blockchain.save_chain_to_file('data_blockchain/blockchain_data1.json')
    print("Chain Data:", blockchain_data["chain"])
    print("Connected Peers:", blockchain_data["peers"])
    return jsonify(blockchain_data), 200

@app.route('/register_node', methods=['POST'])
def register_node_route():
    try:
        data = request.get_json()
        new_node_data = data.get('new_node', {})

        required_fields = ['ip', 'port']
        if any(field not in new_node_data for field in required_fields):
            return jsonify({"error": "Invalid new node data format"}), 400

        new_node = (new_node_data['ip'], new_node_data['port'])
        blockchain.add_peer(new_node)
        print(f"Registered new node: {new_node}")

        return jsonify({"status": "New node registered"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/receive_block', methods=['POST'])
def receive_block():
    try:
        data = request.get_json()
        block_data = data.get('block', {})

        required_fields = ['index', 'timestamp', 'transactions', 'previous_hash']
        if any(field not in block_data for field in required_fields):
            return jsonify({"error": "Invalid block data format"}), 400

        index = block_data['index']
        timestamp = block_data['timestamp']
        transactions_data = block_data['transactions']
        previous_hash = block_data['previous_hash']

        transactions = [Transaction(node_id=txn["node_id"], generic_data=txn["generic_data"], timestamp=txn["timestamp"]) for txn in transactions_data]

        new_block = Block(index=index, timestamp=timestamp, transactions=transactions, previous_hash=previous_hash)

        # Check if the block is not already in the blockchain
        if any(new_block.timestamp == block.timestamp for block in blockchain.chain):
            print(f"Block with timestamp {timestamp} already exists in the blockchain")
            return jsonify({"error": "Block with the same timestamp already in the blockchain"}), 409
        else:
            # Move the chain state to "PREPARE"
            blockchain.state = "PREPARE"
            blockchain.send_prepare_message()
            if blockchain.block_is_valid:
                blockchain.chain.append(new_block)
                blockchain.block_is_valid = False
            else:
                print("Block was not added")

            # Print the received block
            print(f"Received Block: {block_data}")

            # Return status and success message
            return jsonify({"status": "Block received and chain state changed to PREPARE"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "pong"}), 200

@app.route('/prepare_messages', methods=['GET'])
def get_prepare_messages():

    try:
        # Return all prepare messages in the response
        return jsonify({"prepare_messages": blockchain.prepare_messages}), 200

    except Exception as e:
        # Return an error response if an exception occurs
        return jsonify({"error": str(e)}), 500


# Function to handle receiving prepare messages from other nodes
@app.route('/prepare', methods=['POST'])
def receive_prepare_message():

    try:
        data = request.get_json()

        # Add the received prepare message to the list
        blockchain.prepare_messages.append(data)

        # Return a success response
        return jsonify({"status": "Prepare message received successfully"}), 200

    except Exception as e:
        # Return an error response if an exception occurs
        return jsonify({"error": str(e)}), 500


@app.route('/commit_messages', methods=['GET'])
def get_commit_messages():
    try:
        # Return all prepare messages in the response
        return jsonify({"commit_messages": blockchain.commit_messages}), 200

    except Exception as e:
        # Return an error response if an exception occurs
        return jsonify({"error": str(e)}), 500


# Function to handle receiving prepare messages from other nodes
@app.route('/commit', methods=['POST'])
def receive_commit_message():
    try:
        data = request.get_json()

        # Add the received prepare message to the list
        blockchain.commit_messages.append(data)

        # Return a success response
        return jsonify({"status": "Commit message received successfully"}), 200

    except Exception as e:
        # Return an error response if an exception occurs
        return jsonify({"error": str(e)}), 500

# Example Usage:
if __name__ == "__main__":
    # Display the blockchain
    app.run(host=ip, port=port, debug=True)
