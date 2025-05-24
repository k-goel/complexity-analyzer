from flask import Flask, request, jsonify, render_template
import ast

app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

class ComplexityAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.loop_depth = 0
        self.max_depth = 0
        self.function_calls = 0
        self.recursive_calls = 0
        self.function_defs = set()
        self.current_function = None
        self.multiple_recursive_calls_in_same_expr = False

    def visit_For(self, node):
        loop_is_constant = False

        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name):
            if node.iter.func.id == 'range' and len(node.iter.args) == 1:
                arg = node.iter.args[0]
                if isinstance(arg, ast.Constant):
                    loop_is_constant = True

        if not loop_is_constant:
            self.loop_depth += 1
            self.max_depth = max(self.max_depth, self.loop_depth)

        self.generic_visit(node)

        if not loop_is_constant:
            self.loop_depth -= 1

    def visit_While(self, node):
        self.loop_depth += 1
        self.max_depth = max(self.max_depth, self.loop_depth)
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_FunctionDef(self, node):
        self.function_defs.add(node.name)
        prev_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = prev_function

    def visit_Call(self, node):
        self.function_calls += 1
        if isinstance(node.func, ast.Name):
            if node.func.id == self.current_function:
                self.recursive_calls += 1
        self.generic_visit(node)

    def visit_Return(self, node):
        recursive_calls = []

        class CallCollector(ast.NodeVisitor):
            def __init__(self, current_function):
                self.current_function = current_function

            def visit_Call(self, call_node):
                if isinstance(call_node.func, ast.Name) and call_node.func.id == self.current_function:
                    recursive_calls.append(call_node)
                self.generic_visit(call_node)

        CallCollector(self.current_function).visit(node.value)
        
        if len(recursive_calls) >= 2:
            self.multiple_recursive_calls_in_same_expr = True

        self.generic_visit(node)



def analyze_code(code):
    try:
        tree = ast.parse(code)
        analyzer = ComplexityAnalyzer()
        analyzer.visit(tree)

        result = {
            "loops_detected": analyzer.max_depth,
            "function_calls": analyzer.function_calls,
            "recursive_calls": analyzer.recursive_calls,
            "estimated_time_complexity": estimate_complexity(analyzer)
        }
        return result

    except Exception as e:
        return {"error": str(e)}


def estimate_complexity(analyzer):
    depth = analyzer.max_depth
    rec = analyzer.recursive_calls
    multi_rec = analyzer.multiple_recursive_calls_in_same_expr

    # Recursive cases
    if rec > 0:
        if multi_rec:
            return "O(2^n) (branching recursion)"
        elif depth >= 1:
            return "O(n log n) (likely divide and conquer)"
        else:
            return "O(n) to O(n log n) (linear recursion)"

    # Iterative cases
    if depth >= 3:
        return "O(n^3) or higher"
    elif depth == 2:
        return "O(n^2)"
    elif depth == 1:
        return "O(n)"
    else:
        return "O(1) or constant time"


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    code = data.get('code')
    if not code:
        return jsonify({"error": "No code provided"}), 400

    result = analyze_code(code)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True)
