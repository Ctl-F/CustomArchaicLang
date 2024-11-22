from lark import Lark
import lark
from enum import Enum
from dataclasses import dataclass, field
import os

class ObjectType(Enum):
    Undefined = 0
    Library = 1
    Process = 2
    Test = 3

class OptimizationLevel(Enum):
    Debug = 0
    LowOptimization = 1
    HighOptimization = 2

"""
    An ObjectInfo stores all the information about whatever
    "object" we're currently compiling. An object referring to 
    a c-object or a discrete compilation object. Each "lib" "proc"
    and "test" gets compiled to it's own compilation unit (object)

    The object info also stores the compiled c-source that cal translates
    to that will eventually get compiled to the object
"""
@dataclass
class ObjectInfo:
    target_type: ObjectType = ObjectType.Undefined
    target_name: str = ""
    target_functions: list = field(default_factory=lambda: [])
    target_exported_functions: list = field(default_factory=lambda: [])
    target_header_name: str = ""
    target_source_name: str = ""
    target_header_body: list = field(default_factory=lambda: [])
    target_pre_declarations: list = field(default_factory=lambda: [])
    target_source_body: list = field(default_factory=lambda: [])

    def get_name(self):
        match(self.target_type):
            case ObjectType.Undefined:
                return ""
            case ObjectType.Library:
                return "lib%scal" % self.target_name
            case ObjectType.Process:
                return self.target_name
            case ObjectType.Test:
                return "test_%s" % self.target_name
            case _:
                return ""
            
    def update_names(self):
        name = self.get_name()
        self.target_header_name = "%s.h" % name
        self.target_source_name = "%s.c" % name

    def get_local_func(self, name):
        for func in self.target_functions:
            if func["name"] == name:
                return func
        return None

    def export(self):
        for private in self.target_functions:
            name = private["name"]
            params = private["params"]
            returns = private["returns"]

            self.write_pre_decl("static ", returns, " ", name, "(")

            if len(params) == 0:
                self.write_pre_decl("void")

            i = 0
            for type, name in params:
                self.write_pre_decl(type, " ", name)

                if i+1 < len(params):
                    self.write_pre_decl(", ")

            self.write_pre_decl(");\n")
        self.write_pre_decl("\n\n")

        for export in self.target_exported_functions:
            name = export["name"]
            params = export["params"]
            returns = export["returns"]
            link = export["link"]
            link_fn = self.get_local_func(link)

            self.write_header(returns, " ", name, "(")


            if len(params) == 0:
                self.write_header("void")

            i = 0
            for type, pname in params:
                self.write_header(type, " ", pname)

                if i+1 < len(params):
                    self.write_header(", ")

            self.write_header(");\n\n")

            self.write_pre_decl(returns, " ", name, "(")
            i = 0
            for type, pname in params:
                self.write_pre_decl(type, " ", pname)

                if i + 1 < len(params):
                    self.write_pre_decl(", ")

            self.write_pre_decl(") {\n")

            if link_fn["returns"] != "void":
                self.write_pre_decl("    return ")
            self.write_pre_decl("    ", link_fn["name"], "(")

            i = 0
            for type, name in params:
                self.write_pre_decl(name)

                if i + 1 < len(params):
                    self.write_pre_decl(", ")

            self.write_pre_decl(");\n")
            self.write_pre_decl("}\n\n")


        self.write_header("#endif\n\n")

        


        with open(self.target_header_name, "w") as f:
            f.write("".join(self.target_header_body))

        with open(self.target_source_name, "w") as f:
            f.write("".join(self.target_pre_declarations))
            f.write("".join(self.target_source_body))

    def write_header(self, *what):
        for arg in what:
            self.target_header_body.append(arg)

    def write_source(self, *what):
        for arg in what:
            self.target_source_body.append(arg)

    def write_pre_decl(self, *what):
        for arg in what:
            self.target_pre_declarations.append(arg)

    def compile(self, **kwargs):
        #kw_args = kwargs.items()

        compiler = "gcc"
        object_name = "%s.o" % self.get_name()
        optimizations = "-g"
        target_dir = "./bin/"
        keep_source = False

        if "compiler" in kwargs:
            compiler = kwargs["compiler"]

        if "name" in kwargs:
            object_name = kwargs["name"]

        if "optimization" in kwargs:
            olevel = kwargs["optimization"]
            match olevel:
                case OptimizationLevel.Debug:
                    optimizations = "-g"
                case OptimizationLevel.LowOptimization:
                    optimizations = "-g -O1"
                case OptimizationLevel.HighOptimization:
                    optimizations = "-O2"

        if "keep_source" in kwargs:
            keep_source = kwargs["keep_source"]

        if "target_dir" in kwargs:
            target_dir = kwargs["target_dir"]

        if not os.path.exists(target_dir):
            os.mkdir(target_dir)

        compile_only = "-c" if self.target_type == ObjectType.Library else ""

        command = "%s %s -o %s%s %s %s" % (compiler, compile_only, target_dir, object_name, self.target_source_name, optimizations)
        print(command)
        os.system(command)

        if not keep_source:
            os.remove(self.target_header_name)
            os.remove(self.target_source_name)


"""
    The compiler class will take the parsed tree
    and transform it into a series of ObjectInfos with the correct
    compiled c-source. [Cal -> C, C -> bin]
"""
class Compiler:
    def __init__(self):
        self.current_object = None
        self.compilation_args = None

    def compile(self, tree, **kw_args):
        self.compilation_args = kw_args

        if tree.data == "begin_lib":
            self.compile_lib(tree)
        elif tree.data == "begin_proc":
            self.compile_proc(tree)
        elif tree.data == "begin_test":
            self.compile_test(tree)
        elif tree.data == "start":
            for item in tree.children:
                self.compile(item)

    def compile_lib(self, lib_node):
        self.current_object = ObjectInfo(target_type=ObjectType.Library)
        self.current_object.target_name = str(lib_node.children[0])
        self.current_object.update_names()

        obj_name = self.current_object.get_name()
        self.current_object.write_header("#ifndef ", obj_name, "_h\n#define ", obj_name, "_h\n")
        self.current_object.write_pre_decl("#include \"", self.current_object.target_header_name, "\"\n\n")

        self.compile_code_unit(lib_node.children[1])

        self.current_object.export()
        self.current_object.compile(**self.compilation_args)

    def compile_proc(self, proc_node):
        pass

    def compile_test(self, test_node):
        pass

    def compile_code_unit(self, unit_body):
        self.current_object.write_header("#include <stdint.h>\n")
        self.current_object.write_header("#include <stdbool.h>\n")

        for item in unit_body.children:
            match item.data:
                case "c_include":
                    self.compile_c_include(item)
                case "function":
                    self.compile_function(item)
                case _:
                    print("Error compiling code unit, unexpected item %s" % item)

    def compile_c_include(self, c_include):
        self.current_object.write_source("#include <", str(c_include.children[0])[1:-1], ">\n")

    def compile_function(self, func_node):
        cursor = 0
        is_global = False
        if func_node.children[cursor] == "glob":
            is_global = True
            cursor += 1
        name = str(func_node.children[cursor])
        cursor += 1
        params = self.get_params(func_node.children[cursor])

        cursor += 1

        return_type = "void"

        if not (type(func_node.children[cursor]) is lark.tree.Tree):
            return_type = self.get_c_type(str(func_node.children[cursor]))
            cursor += 1

        if is_global:
            glob_name = "%s_%s" % (self.current_object.target_name, name)
            self.current_object.target_exported_functions.append( { "name": glob_name, "params": params, "returns": return_type, "link": name })
        
        self.current_object.target_functions.append({ "name": name, "params": params, "returns": return_type })

        if not is_global:
            self.current_object.write_source("static ")
        self.current_object.write_source(return_type, " ", name)
        self.current_object.write_source("(")

        i = 0
        for type_, name in params:
            self.current_object.write_source(type_, " ", name)
            if i+1 < len(params):
                self.current_object.write_source(", ")
            else:
                self.current_object.write_source(" ")
            i += 1

        self.current_object.write_source(")")

        self.compile_function_body(func_node.children[cursor])

    def get_c_type(self, type):
        match type:
            case ".i32":
                return "int32_t"
            case ".i8":
                return "int8_t"
            case ".i16":
                return "int16_t"
            case ".i64":
                return "int64_t"
            case ".f32":
                return "float"
            case ".f64":
                return "double"
            case ".cstr":
                return "char*"
            case ".ptr":
                return "void*"
            case ".byte_ptr":
                return "int8_t*"
            case ".word_ptr":
                return "int16_t*"
            case ".dword_ptr":
                return "int32_t*"
            case ".qword_ptr":
                return "int64_t*"
            case "":
                return "void"
            case None:
                return "void"
            case "void":
                return "void"
            case _:
                print("Unknown type %s" % type)

    def get_params(self, params_list):
        params = []

        if params_list == None:
            return []

        for param in params_list.children:
            type = self.get_c_type(str(param.children[0]))
            name = str(param.children[1])
            params.append((type, name))
        return params

    def compile_function_body(self, body_node):
        self.current_object.write_source("{\n")

        for item in body_node.children:
            self.current_object.write_source("    ")
            try:
                match item.data:
                    case "stack_allocation":
                        self.compile_stack_alloc(item)
                    case "raw_c_statement":
                        self.compile_inline_c(item)
                    case "return_statement":
                        self.compile_return(item)
                    case "expression":
                        self.compile_expression(item)
                        self.current_object.write_source(";\n")
            except AttributeError:
                print("Unexpected item %s" % item)

        self.current_object.write_source("}\n\n")


    def compile_return(self, return_node):
        self.current_object.write_source("return ")

        if len(return_node.children) > 0:
            self.compile_expression(return_node.children[0])
        
        self.current_object.write_source(";\n")

    def compile_expression(self, expression):
        expr = expression
        if expr.data == "expression":
            expr = expr.children[0]

        match expr.data:
            case "plus_eq":
                self.compile_plus_eq(expr)
            case "minus_eq":
                self.compile_minus_eq(expr)
            case "mul_eq":
                self.compile_mul_eq(expr)
            case "div_eq":
                self.compile_div_eq(expr)
            case "mod_eq":
                self.compile_mod_eq(expr)
            case "assign":
                self.compile_assign(expr)
            case "logic_equals":
                self.compile_logic_equals(expr)
            case "logic_notequals":
                self.compile_logic_notequals(expr)
            case "logic_and":
                self.compile_logic_and(expr)
            case "logic_or":
                self.compile_logic_or(expr)
            case "logic_ge":
                self.compile_logic_ge(expr)
            case "logic_le":
                self.compile_logic_le(expr)
            case "logic_gt":
                self.compile_logic_gt(expr)
            case "logic_lt":
                self.compile_logic_lt(expr)
            case "add":
                self.compile_add(expr)
            case "sub":
                self.compile_sub(expr)
            case "mul":
                self.compile_mul(expr)
            case "div":
                self.compile_div(expr)
            case "mod":
                self.compile_mod(expr)
            case "neg":
                self.compile_neg(expr)
            case "not":
                self.compile_not(expr)
            case "func_call":
                self.compile_func_call(expr)
            case "var":
                self.compile_var(expr)
            case "deref_var":
                self.compile_deref_var(expr)
            case "deref_func_call":
                self.compile_deref_func_call(expr)
            case "post_inc":
                self.compile_post_inc(expr)
            case "post_dec":
                self.compile_post_dec(expr)
            case "pre_inc":
                self.compile_pre_inc(expr)
            case "pre_dec":
                self.compile_pre_dec(expr)
            case "group":
                self.compile_group(expr)
            case "value":
                self.compile_value(expr)

    def compile_plus_eq(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" += ")
        self.compile_expression(node.children[1])

    def compile_minus_eq(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" -= ")
        self.compile_expression(node.children[1])

    def compile_mul_eq(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" *= ")
        self.compile_expression(node.children[1])

    def compile_div_eq(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" /= ")
        self.compile_expression(node.children[1])

    def compile_mod_eq(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" %= ")
        self.compile_expression(node.children[1])

    def compile_assign(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" = ")
        self.compile_expression(node.children[1])


    def compile_logic_equals(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" == ")
        self.compile_expression(node.children[1])

    def compile_logic_notequals(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" != ")
        self.compile_expression(node.children[1])

    def compile_logic_and(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" && ")
        self.compile_expression(node.children[1])

    def compile_logic_or(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" || ")
        self.compile_expression(node.children[1])

    def compile_logic_ge(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" >= ")
        self.compile_expression(node.children[1])

    def compile_logic_le(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" <= ")
        self.compile_expression(node.children[1])

    def compile_logic_gt(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" > ")
        self.compile_expression(node.children[1])

    def compile_logic_lt(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" < ")
        self.compile_expression(node.children[1])

    def compile_add(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" + ")
        self.compile_expression(node.children[1])

    def compile_sub(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" - ")
        self.compile_expression(node.children[1])

    def compile_mul(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" * ")
        self.compile_expression(node.children[1])

    def compile_div(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" / ")
        self.compile_expression(node.children[1])

    def compile_mod(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" % ")
        self.compile_expression(node.children[1])

    def compile_neg(self, node):
        self.current_object.write_source(" -")
        self.compile_expression(node.children[0])

    def compile_not(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" !")
        self.compile_expression(node.children[0])

    def compile_func_call(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source("(")

        for i in range(1, len(node.children)):
            self.compile_expression(node.children[i])

            if i + 1 < len(node.children):
                self.current_object.write_source(", ")

        self.current_object.write_source(")")

    def compile_var(self, node):
        var_name = ""
        if node.children[0] != None:
            var_name = "%s_%s" % (node.children[0], node.children[1])
        else:
            var_name = str(node.children[1])

        self.current_object.write_source(var_name)

    def compile_deref_var(self, node):
        pass

    def compile_deref_func_call(self, node):
        pass

    def compile_post_inc(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source("++ ")

    def compile_post_dec(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source("-- ")

    def compile_pre_inc(self, node):
        self.current_object.write_source(" ++")
        self.compile_expression(node.children[0])

    def compile_pre_dec(self, node):
        self.current_object.write_source(" --")
        self.compile_expression(node.children[0])

    def compile_group(self, node):
        self.current_object.write_source("(")
        self.compile_expression(node.children[0])
        self.current_object.write_source(")")

    def compile_value(self, node):
        self.current_object.write_source(str(node.children[0]))



    def compile_stack_alloc(self, alloc_node):
        c_type = self.get_c_type(str(alloc_node.children[0]))
        c_name = str(alloc_node.children[1])

        is_ptr = c_type[-1] == '*'

        if alloc_node.children[2] != None:
            value_node = alloc_node.children[2]
            
            if is_ptr and value_node.data == "static_array":
                self.current_object.write_source(c_type[:-1], " ", c_name, "[]")
            else:
                self.current_object.write_source(c_type, " ", c_name)
            
            self.current_object.write_source(" = ")
            if value_node.data == "static_array":
                self.current_object.write_source("{")

                for child in value_node.children:
                    ## I Don't know if it's possible for a child in this scenario to have
                    ## more than 1 child
                    self.current_object.write_source(str(child.children[0]), ", ")

                self.current_object.write_source("}")
            else:
                self.current_object.write_source(str(value_node.children[0]))
        else:
            self.current_object.write_source(c_type, " ", c_name)

        self.current_object.write_source(";\n")

    def compile_inline_c(self, inline_c):
        raw_c = inline_c.children[0]
        c_code = str(raw_c)[4:-2]
        self.current_object.write_source(c_code.strip(), "\n")

with open("grammar.lark", "r") as f:
    Grammar = f.read()

def main():
    global Grammar
    code = ""
    with open("example.cal", "r") as f:
        code = f.read()

    parser = Lark(Grammar, parser="lalr", maybe_placeholders=True)
    parsed = parser.parse(code)
    print(parsed.pretty())

    compiler = Compiler()
    compiler.compile(parsed, keep_source=True)


if __name__ == "__main__":
    main()
