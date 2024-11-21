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

    def export(self):

        for export in self.target_exported_functions:
            name = export["name"]
            params = export["params"]
            returns = export["returns"]

            self.write_header(returns, " ", name, "(")

            i = 0
            for type, name in params:
                self.write_header(type, " ", name)

                if i+1 < len(params):
                    self.write_header(", ")
                else:
                    self.write_header(" ")

            self.write_header(");\n")
        self.write_header("#endif\n\n")

        for private in self.target_functions:
            name = private["name"]
            params = private["params"]
            returns = private["returns"]

            self.write_pre_decl("static ", returns, " ", name, "(")

            i = 0
            for type, name in params:
                self.write_pre_decl(type, " ", name)

                if i+1 < len(params):
                    self.write_pre_decl(", ")
                else:
                    self.write_pre_decl(" ")

            self.write_pre_decl(");\n")

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
        kw_args = kwargs.items()

        compiler = "gcc"
        object_name = "%s.o" % self.get_name()
        optimizations = "-g"
        target_dir = "./bin/"

        if "compiler" in kw_args:
            compiler = kw_args["compiler"]

        if "name" in kw_args:
            object_name = kw_args["name"]

        if "optimization" in kw_args:
            olevel = kw_args["optimization"]
            match olevel:
                case OptimizationLevel.Debug:
                    optimizations = "-g"
                case OptimizationLevel.LowOptimization:
                    optimizations = "-g -O1"
                case OptimizationLevel.HighOptimization:
                    optimizations = "-O2"

        if "target_dir" in kw_args:
            target_dir = kw_args["target_dir"]

        compile_only = "-c" if self.target_type == ObjectType.Library else ""

        command = "%s %s -o %s%s %s" % (compiler, compile_only, target_dir, object_name, optimizations)
        os.system(command)


"""
    The compiler class will take the parsed tree
    and transform it into a series of ObjectInfos with the correct
    compiled c-source. [Cal -> C, C -> bin]
"""
class Compiler:
    def __init__(self):
        self.current_object = None

    def compile(self, tree):
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
        self.current_object.compile()

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
            self.current_object.target_exported_functions.append( { "name": name, "params": params, "returns": return_type })
        else:
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
            try:
                match item.data:
                    case "stack_allocation":
                        self.compile_stack_alloc(item)
                    case "raw_c_statement":
                        self.compile_inline_c(item)
            except AttributeError:
                print("Unexpected item %s" % item)

        self.current_object.write_source("}\n\n")

    def compile_stack_alloc(self, alloc_node):
        c_type = self.get_c_type(str(alloc_node.children[0]))
        c_name = str(alloc_node.children[1])

        self.current_object.write_source(c_type, " ", c_name)

        if alloc_node.children[2] != None:
            self.current_object.write_source(" = ")
            value_node = alloc_node.children[2]
            if value_node.data == "static_array":
                self.current_object.write_source("{")

                for child in value_node.children:
                    ## I Don't know if it's possible for a child in this scenario to have
                    ## more than 1 child
                    self.current_object.write_source(str(child.children[0]), ", ")

                self.current_object.write_source("}")
            else:
                self.current_object.write_source(str(value_node.children[0]))

        self.current_object.write_source(";\n")

    def compile_inline_c(self, inline_c):
        raw_c = inline_c.children[0]
        c_code = str(raw_c)[4:-2]
        self.current_object.write_source(c_code, "\n")

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
    compiler.compile(parsed)


if __name__ == "__main__":
    main()
