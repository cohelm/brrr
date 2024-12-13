import os
import http
import json
import socketserver

from brrr.brrr import Brrr, Task
from brrr.store import Call

class Srrrver(http.server.SimpleHTTPRequestHandler):
    """
    A "Front Office" worker, that is publically exposed and takes requests
    to schedule tasks and return their results via webhooks
    """
    brrr: Brrr

    @classmethod
    def subclass_with_brrr(cls, brrr: Brrr) -> 'Srrrver':
        """
        For some reason the python server class needs to be instantiated without args
        """
        return type("SrrrverWithBrrr", (cls,), {"brrr": brrr})

    """
    A simple HTTP server that takes a JSON payload and schedules a task
    """
    def do_GET(self):
        """
        GET /task_name?argv={"..."}
        """
        task_name = self.path.split("?")[0].strip("/")
        # TODO parse the argv properly
        kwargs = dict(parse_qsl(self.path.split("?")[-1]))
        argv = ((), kwargs)

        try:
            task = self.brrr.tasks[task_name]
            call = Call(task.name, argv)
        except KeyError:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Task not found"}).encode())
            return

        try:
            memo_key = call.memo_key
            result = self.brrr.memory.get_value(memo_key)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "result": result}).encode())
        except KeyError:
            self.brrr.schedule(call)
            self.send_response(202)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "accepted"}).encode())
            return

    def do_POST(self):
        """
        POST /{task_name} with a JSON payload {
            "args": [],
            "kwargs": {},
        }

        """
        # Custom behavior for POST requests
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        self.wfile.write(post_data)

        # Schedule a task and submit PUT request to the webhook with the result if one is provided
        # once it's done
        try:
            data = json.loads(post_data)
            call = Call(data["task_name"], (data["args"], data["kwargs"]))
            frame = self.brrr.schedule(call)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {"status": "OK", "frame_key": frame.frame_key}
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {"error": "Invalid JSON"}
            self.wfile.write(json.dumps(error_response))

    @classmethod
    def srrrv(cls, brrr: Brrr, port: int = int(os.getenv("SRRRVER_PORT", "8333"))):
        """
        Spin up a webserver that that translates HTTP requests to tasks
        """
        # Srrrver.tasks.update({task.name: task for task in tasks})
        with socketserver.TCPServer(("", port), cls.subclass_with_brrr(brrr)) as httpd:
            print(f"Srrrver running on port {port}")
            print("Available tasks:")
            for task in brrr.tasks.values():
                print("  ", task.name)
            httpd.serve_forever()
