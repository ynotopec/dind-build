#!/usr/bin/env python3
"""
Test script for the DinD Build Factory MCP Server
"""
import subprocess
import json
import sys
import os

MCP_SERVER_PATH = "/home/ai-agent/work/dind-build/dind-mcp-server.py"

def send_jsonrpc(process, message):
    """Send a JSON-RPC message to the MCP server."""
    request = {
        "jsonrpc": "2.0",
        "id": message.get("id", 1),
        "method": message.get("method", ""),
        "params": message.get("params", {})
    }
    json_str = json.dumps(request) + "\n"
    process.stdin.write(json_str)
    process.stdin.flush()
    
    # Wait for response
    import time
    time.sleep(0.5)
    
    # Read response
    if process.stdout:
        response = process.stdout.readline()
        if response:
            return json.loads(response.strip())
    return None

def main():
    print("Starting DinD Build Factory MCP Server for testing...")
    
    # Start the MCP server
    process = subprocess.Popen(
        ["python3", MCP_SERVER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Send initialize request
        print("\n1. Sending initialize request...")
        init_msg = {
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.1.0"}
            }
        }
        
        init_response = send_jsonrpc(process, init_msg)
        if init_response:
            print(f"✓ Initialize response: {json.dumps(init_response, indent=2)[:200]}...")
        else:
            print("✗ No initialize response")
            return
            
        # Send initialized notification
        print("\n2. Sending initialized notification...")
        initialized_msg = {
            "id": 2,
            "method": "notifications/initialized"
        }
        send_jsonrpc(process, initialized_msg)
        
        # List tools
        print("\n3. Requesting tools list...")
        tools_msg = {
            "id": 3,
            "method": "tools/list"
        }
        tools_response = send_jsonrpc(process, tools_msg)
        if tools_response:
            print(f"✓ Tools list response received")
            print(f"  Response keys: {list(tools_response.keys())}")
            if "result" in tools_response:
                result = tools_response["result"]
                print(f"  Result type: {type(result)}")
                if hasattr(result, 'tools'):
                    print(f"  Tools: {result.tools}")
                else:
                    print(f"  Result: {json.dumps(result, indent=2)[:500]}")
        else:
            print("✗ No tools list response")
            
        # Test a tool call
        print("\n4. Testing dind_list_images tool...")
        call_msg = {
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "dind_list_images",
                "arguments": {}
            }
        }
        call_response = send_jsonrpc(process, call_msg)
        if call_response:
            print(f"✓ Tool call response received")
            print(f"  Response keys: {list(call_response.keys())}")
            if "result" in call_response:
                print(f"  Result: {json.dumps(call_response['result'], indent=2)[:500]}...")
        else:
            print("✗ No tool call response")
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close server
        print("\n5. Stopping server...")
        process.stdin.close()
        process.terminate()
        process.wait(timeout=5)
        print("✓ Test complete")

if __name__ == "__main__":
    main()
