from flask import Flask, request, jsonify, render_template
import ast

app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

# NEW analyser with parameter-based complexity
class ParamComplexityanalyser(ast.NodeVisitor):
    def __init__(self):
        self.loop_depth = 0
        self.max_depth = 0
        self.function_calls = 0
        self.recursive_calls = 0
        self.function_defs = set()
        self.current_function = None
        self.multiple_recursive_calls_in_same_expr = False

        self.current_function_params = []
        self.param_complexity = {}

    def visit_For(self, node):
        loop_param = None

        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name):
            if node.iter.func.id == 'range':
                for arg in node.iter.args:
                    if isinstance(arg, ast.Name) and arg.id in self.current_function_params:
                        loop_param = arg.id
                        break

        loop_is_constant = isinstance(node.iter, ast.Call) and isinstance(node.iter.args[0], ast.Constant)

        if not loop_is_constant:
            self.loop_depth += 1
            self.max_depth = max(self.max_depth, self.loop_depth)
            if loop_param:
                self.param_complexity[loop_param]["loops"] += 1

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
        self.current_function_params = [arg.arg for arg in node.args.args]
        self.param_complexity = {
            param: {"loops": 0, "recursions": 0, "branching_rec": False}
            for param in self.current_function_params
        }
        self.generic_visit(node)
        self.current_function = prev_function

    def visit_Call(self, node):
        self.function_calls += 1
        if isinstance(node.func, ast.Name):
            if node.func.id == self.current_function:
                self.recursive_calls += 1
                for arg in node.args:
                    if isinstance(arg, ast.Name) and arg.id in self.current_function_params:
                        self.param_complexity[arg.id]["recursions"] += 1
        self.generic_visit(node)

    def visit_Return(self, node):
        recursive_calls = []

        class CallCollector(ast.NodeVisitor):
            def __init__(self, current_function, current_function_params, param_complexity):
                self.current_function = current_function
                self.current_function_params = current_function_params
                self.param_complexity = param_complexity

            def visit_Call(self, call_node):
                if isinstance(call_node.func, ast.Name) and call_node.func.id == self.current_function:
                    recursive_calls.append(call_node)
                    for arg in call_node.args:
                        if isinstance(arg, ast.Name) and arg.id in self.current_function_params:
                            self.param_complexity[arg.id]["branching_rec"] = True
                self.generic_visit(call_node)

        CallCollector(self.current_function, self.current_function_params, self.param_complexity).visit(node.value)

        if len(recursive_calls) >= 2:
            self.multiple_recursive_calls_in_same_expr = True

        self.generic_visit(node)


class BasicComplexityanalyser(ast.NodeVisitor):
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


# Analysis dispatch
def analyse_code(code):
    try:
        tree = ast.parse(code)

        has_function_defs = any(isinstance(node, ast.FunctionDef) for node in tree.body)

        if has_function_defs:
            analyser = ParamComplexityanalyser()
            analyser.visit(tree)
            per_param_complexity, worst_param, worst_complexity = estimate_param_complexity(analyser.param_complexity)
            result = {
                "loops_detected": analyser.max_depth,
                "function_calls": analyser.function_calls,
                "recursive_calls": analyser.recursive_calls,
                "complexity_per_parameter": per_param_complexity,
                "dominant_parameter": worst_param,
                "estimated_time_complexity": worst_complexity
            }
        else:
            analyser = BasicComplexityanalyser()
            analyser.visit(tree)
            result = {
                "loops_detected": analyser.max_depth,
                "function_calls": analyser.function_calls,
                "recursive_calls": analyser.recursive_calls,
                "estimated_time_complexity": estimate_basic_complexity(analyser)
            }

        return result

    except Exception as e:
        return {"error": str(e)}


# Param-based complexity estimation
def estimate_param_complexity(param_complexity):
    complexities = {}
    complexity_order = {
        "O(1)": 0,
        "O(n)": 1,
        "O(n log n)": 2,
        "O(n^2)": 3,
        "O(n^3) or higher": 4,
        "O(2^n)": 5
    }

    for param, metrics in param_complexity.items():
        loops = metrics["loops"]
        rec = metrics["recursions"]
        branching = metrics["branching_rec"]

        if rec > 0:
            if branching:
                complexities[param] = "O(2^n)"
            elif loops >= 1:
                complexities[param] = "O(n log n)"
            else:
                complexities[param] = "O(n)"
        else:
            if loops >= 3:
                complexities[param] = "O(n^3) or higher"
            elif loops == 2:
                complexities[param] = "O(n^2)"
            elif loops == 1:
                complexities[param] = "O(n)"
            else:
                complexities[param] = "O(1)"

    if complexities:
        worst_param = max(complexities, key=lambda p: complexity_order[complexities[p]])
        worst = complexities[worst_param]
    else:
        worst_param = None
        worst = "O(1)"

    return complexities, worst_param, worst


# Basic complexity estimation
def estimate_basic_complexity(analyser):
    depth = analyser.max_depth
    rec = analyser.recursive_calls
    multi_rec = analyser.multiple_recursive_calls_in_same_expr

    if rec > 0:
        if multi_rec:
            return "O(2^n) (branching recursion)"
        elif depth >= 1:
            return "O(n log n) (likely divide and conquer)"
        else:
            return "O(n) to O(n log n) (linear recursion)"

    if depth >= 3:
        return "O(n^3) or higher"
    elif depth == 2:
        return "O(n^2)"
    elif depth == 1:
        return "O(n)"
    else:
        return "O(1) or constant time"


@app.route('/analyse', methods=['POST'])
def analyse():
    data = request.get_json()
    code = data.get('code')
    if not code:
        return jsonify({"error": "No code provided"}), 400

    result = analyse_code(code)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True)
