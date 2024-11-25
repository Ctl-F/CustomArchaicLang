from lark import Lark
import lark
from enum import Enum
from dataclasses import dataclass, field
import os, sys

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
    target_link_objects: list = field(default_factory=lambda: [])

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
            is_global = private["is_global"]

            if not is_global:
                self.write_pre_decl("static ")
            self.write_pre_decl(returns, " ", name, "(")

            if len(params) == 0:
                self.write_pre_decl("void")

            i = 0
            for type, name in params:
                self.write_pre_decl(type, " ", name)

                if i+1 < len(params):
                    self.write_pre_decl(", ")
                i += 1

            self.write_pre_decl(");\n")
        self.write_pre_decl("\n\n")

        if self.target_type == ObjectType.Library:
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
                    i += 1

                self.write_header(");\n\n")

                self.write_pre_decl(returns, " ", name, "(")
                i = 0
                for type, pname in params:
                    self.write_pre_decl(type, " ", pname)

                    if i + 1 < len(params):
                        self.write_pre_decl(", ")
                    i += 1

                self.write_pre_decl(") {\n")

                if link_fn["returns"] != "void":
                    self.write_pre_decl("    return ")
                self.write_pre_decl("    ", link_fn["name"], "(")

                i = 0
                for type, name in params:
                    self.write_pre_decl(name)

                    if i + 1 < len(params):
                        self.write_pre_decl(", ")
                    i += 1

                self.write_pre_decl(");\n")
                self.write_pre_decl("}\n\n")


            self.write_header("#endif\n\n")

        if self.target_type == ObjectType.Library:
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
        object_name = self.get_name()

        if self.target_type == ObjectType.Library:
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

        links = ""
        for link in self.target_link_objects:
            links += "%slib%scal.o " % (target_dir, link)

        compile_only = "-c" if self.target_type == ObjectType.Library else ""

        command = "%s %s -o %s%s %s %s %s" % (compiler, compile_only, target_dir, object_name, self.target_source_name, links, optimizations)
        print(command)
        os.system(command)

        #if not keep_source and self.target_type == ObjectType.Library:
        #    os.remove(self.target_source_name)


def sort_objects(item):
    if item.data == "begin_lib":
        return -1
    return 1
    
    

"""
    The compiler class will take the parsed tree
    and transform it into a series of ObjectInfos with the correct
    compiled c-source. [Cal -> C, C -> bin]
"""
class Compiler:
    def __init__(self):
        self.current_object = None
        self.compilation_args = None
        self.for_counter = 0
        self.while_counter = 0
        self.break_labels = [ None ]
        self.delta = 0

    def compile(self, tree, **kw_args):
        self.compilation_args = kw_args

        if tree.data == "begin_lib":
            self.compile_lib(tree)
        elif tree.data == "begin_proc":
            self.compile_proc(tree)
        elif tree.data == "begin_test":
            self.compile_test(tree)
        elif tree.data == "start":
            ls = sorted(tree.children, key=sort_objects)
            for item in ls:
                self.compile(item)

    def compile_lib(self, lib_node):
        self.while_counter = 0
        self.for_counter = 0

        self.current_object = ObjectInfo(target_type=ObjectType.Library)
        self.current_object.target_name = str(lib_node.children[0])
        self.current_object.update_names()

        obj_name = self.current_object.get_name()
        print("Compiling library: %s" % obj_name)

        self.current_object.write_header("#ifndef ", obj_name, "_h\n#define ", obj_name, "_h\n")
        self.current_object.write_pre_decl("#include \"", self.current_object.target_header_name, "\"\n\n")

        self.compile_code_unit(lib_node.children[1])

        self.current_object.export()
        self.current_object.compile(**self.compilation_args)

        print("done.")

    def compile_proc(self, proc_node):
        self.while_counter = 0
        self.for_counter = 0

        self.current_object = ObjectInfo(target_type=ObjectType.Process)
        self.current_object.target_name = str(proc_node.children[0])
        self.current_object.update_names()

        obj_name = self.current_object.get_name()
        print("Compiling process: %s" % obj_name)

        #handle the key-value definitions in tye proc list

        self.current_object.write_pre_decl("#include <stdint.h>\n#include <stdbool.h>\n\n")

        self.compile_code_unit(proc_node.children[2])

        self.current_object.export()
        self.current_object.compile(**self.compilation_args)

        print("done.")

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
                case "static_allocation":
                    self.compile_static_allocation(item)
                case "link":
                    self.compile_link(item)
                case _:
                    print("Error compiling code unit, unexpected item %s" % item)

            self.current_object.write_source("\n");

    def compile_link(self, link_node):
        for link in link_node.children:
            spoof = ObjectInfo(ObjectType.Library)
            spoof.target_name = str(link)
            spoof.update_names()

            self.current_object.target_link_objects.append(spoof.target_name)
            self.current_object.write_pre_decl("#include \"%s\"\n" % spoof.target_header_name)
        

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
        
        self.current_object.target_functions.append({ "name": name, "params": params, "returns": return_type, "is_global": is_global })

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

        self.compile_code_body(func_node.children[cursor])

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
            case ".i8_ptr":
                return "int8_t*"
            case ".i16_ptr":
                return "int16_t*"
            case ".i32_ptr":
                return "int32_t*"
            case ".i64_ptr":
                return "int64_t*"
            case ".f32_ptr":
                return "float*"
            case ".f64_ptr":
                return "double"
            case "":
                return "void"
            case None:
                return "void"
            case "void":
                return "void"
            case ".ptr_ptr":
                return "void**"
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

    def compile_statement(self, item):
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
                case "if_statement":
                    self.compile_if(item)
                case "else_if":
                    self.compile_else_if(item)
                case "else":
                    self.compile_else(item)
                case "break":
                    self.compile_break()
                case "continue":
                    self.compile_continue()
                case "while_statement":
                    self.compile_while(item)
                case "do_while_statement":
                    self.compile_do_while(item)
                case "for_statement":
                    self.compile_for(item)

        except AttributeError:
            print("Unexpected item %s" % item)

    def compile_code_body(self, body_node):
        self.current_object.write_source("{\n")

        for item in body_node.children:
            self.compile_statement(item)

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
            case "ref":
                self.compile_ref(expr)
            case "bin_or":
                self.compile_bin_or(expr)
            case "bin_and":
                self.compile_bin_and(expr)
            case "bin_xor":
                self.compile_bin_xor(expr)
            case "bin_rshift":
                self.compile_bin_rshift(expr)
            case "bin_lshift":
                self.compile_bin_lshift(expr)
            case "bin_not":
                self.compile_bin_not(expr)
            case "macro_sizeof":
                self.compile_macro_sizeof(expr)
            case "argument_list":
                idx = 0
                for child in expr.children:
                    self.compile_expression(child)
                    if idx+1 < len(expr.children):
                        self.current_object.write_source(", ")
                    idx += 1

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

    def compile_bin_or(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" | ")
        self.compile_expression(node.children[1])

    def compile_bin_and(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" & ")
        self.compile_expression(node.children[1])

    def compile_bin_xor(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" ^ ")
        self.compile_expression(node.children[1])

    def compile_bin_rshift(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" >> ")
        self.compile_expression(node.children[1])

    def compile_bin_lshift(self, node):
        self.compile_expression(node.children[0])
        self.current_object.write_source(" << ")
        self.compile_expression(node.children[1])

    def compile_bin_not(self, node):
        self.current_object.write_source(" ~")
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

    def compile_macro_buffer_bytes(self, static_keyword, c_type, c_name, node):
        buffer_name = "_CAL__buffer%s___" % self.delta
        self.delta += 1

        self.current_object.write_source(static_keyword, "char %s[%s] = {" % (buffer_name, node.children[0]), "0", "};\n")

        if static_keyword == "":
            self.current_object.write_source("    ")

        self.current_object.write_source(static_keyword, c_type, " ", c_name, " = ", buffer_name, ";\n")


    def compile_macro_buffer_typed(self, static_keyword, c_type, c_name, node):
        buffer_name = "_CAL__buffer%s___" % self.delta
        self.delta += 1

        buffer_type = self.get_c_type(str(node.children[0]))
        buffer_count = str(node.children[1])

        self.current_object.write_source(static_keyword, buffer_type, " ", buffer_name, "[", buffer_count, "] = {", "0", "};\n")

        if static_keyword == "":
            self.current_object.write_source("    ")
        
        self.current_object.write_source(static_keyword, c_type, " ", c_name, " = ", buffer_name, ";\n")

    def compile_macro_buffer_struct(self, static_keyword, c_type, c_name, node):
        buffer_name = "_CAL_buffer%s___" % self.delta
        self.delta += 1
        # TEST THIS STILL
        struct_name = str(node.children[1])

        if node.children[0] != None:
            struct_name = "%s_%s" % (node.children[0], struct_name)
        
        buffer_count = str(node.children[2])

        self.current_object.write_source(static_keyword, struct_name, " ", buffer_name, "[", buffer_count, "] = {", "0", "};\n")

        if static_keyword == "":
            self.current_object.write_source("    ")
        
        self.current_object.write_source(static_keyword, c_type, " ", c_name, " = ", buffer_name, ";\n")

    def compile_cast(self, node):
        cast_type = self.get_c_type(str(node))
        self.current_object.write_source("(%s)" % cast_type)

    def compile_deref_var(self, node):
        cast = node.children[0]
        name_ext = node.children[1]
        name = node.children[2]

        static_offsets = []
        for i in range(3, len(node.children)):
            static_offsets.append(node.children[i])

        self.current_object.write_source("*")

        if cast != None:
            self.compile_cast(cast)

        var_name = str(name)

        if name_ext != None:
            var_name = "%s_%s" % (name_ext, var_name)

        self.current_object.write_source("(")

        self.current_object.write_source(var_name)

        for offset in static_offsets:
            if offset.data == "static_plus":
                self.current_object.write_source("+")
            elif offset.data == "static_minus":
                self.current_object.write_source("-")
            else:
                print("Unexpected offset token %s" % offset.data);
            
            try:
                self.compile_expression(offset.children[0])
            except:
                self.current_object.write_source(str(offset.children[0]))

        self.current_object.write_source(")")

    def compile_deref_func_call(self, node):
        cast = node.children[0]
        func_call = node.children[1]

        static_offsets = []
        for i in range(2, len(node.children)):
            static_offsets.append(node.children[i])

        self.current_object.write_source("*")

        if cast != None:
            self.compile_cast(cast)
        
        self.current_object.write_source("(")

        self.compile_expression(func_call)

        for offset in static_offsets:
            if offset.data == "static_plus":
                self.current_object.write_source("+")
            elif offset.data == "static_minus":
                self.current_object.write_source("-")
            else:
                print("Unexpected offset token %s" % offset.data)
            
            try:
                self.compile_expression(offset.children[0])
            except:
                self.current_object.write_source(str(offset.children[0]))
        
        self.current_object.write_source(")")

    def compile_ref(self, node):
        self.current_object.write_source("&")
        self.compile_expression(node.children[0])

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

    def compile_static_allocation(self, alloc_node):
        self.compile_allocation(alloc_node, True)

    def compile_stack_alloc(self, alloc_node):
        self.compile_allocation(alloc_node, False)

    def compile_allocation(self, alloc_node, is_static):
        c_type = self.get_c_type(str(alloc_node.children[0]))
        c_name = str(alloc_node.children[1])

        is_ptr = c_type[-1] == '*'

        static_keyword = "static " if is_static else ""

        if alloc_node.children[2] != None:
            value_node = alloc_node.children[2]
            
            if is_ptr and value_node.data == "static_array":
                self.current_object.write_source(static_keyword, c_type[:-1], " ", c_name, "[]")
            elif is_ptr and value_node.data == "macro_buffer_bytes_alloc":
                self.compile_macro_buffer_bytes(static_keyword, c_type, c_name, value_node)
                return
            elif is_ptr and value_node.data == "macro_buffer_typed_alloc":
                self.compile_macro_buffer_typed(static_keyword, c_type, c_name, value_node)
                return
            elif is_ptr and value_node.data == "macro_buffer_struct_alloc":
                self.compile_macro_buffer_struct(static_keyword, c_type, c_name, value_node)
                return
            else:
                self.current_object.write_source(static_keyword, c_type, " ", c_name)
            
            self.current_object.write_source(" = ")

            if value_node.data == "static_array":
                self.compile_static_array(value_node)
            else:
                self.current_object.write_source(str(value_node.children[0]))
        else:
            self.current_object.write_source(c_type, " ", c_name)

        self.current_object.write_source(";\n")

    def compile_static_array(self, value_node):
        self.current_object.write_source("{")

        i = 0
        for child in value_node.children:
            ## I Don't know if it's possible for a child in this scenario to have
            ## more than 1 child
            self.current_object.write_source(str(child.children[0]))
            if i + 1 < len(value_node.children):
                self.current_object.write_source(", ")
            i += 1

        self.current_object.write_source("}")

    def compile_inline_c(self, inline_c):
        raw_c = inline_c.children[0]
        c_code = str(raw_c)[4:-2]
        self.current_object.write_source(c_code.strip(), "\n")

    def compile_macro_sizeof(self, node):
        c_type = self.get_c_type(str(node.children[0]))
        self.current_object.write_source("sizeof(%s)" % c_type)

    def compile_if(self, node):
        self.current_object.write_source("if (")
        self.compile_expression(node.children[0])
        self.current_object.write_source("){\n")

        else_branch = None

        for i in range(1, len(node.children)):
            if node.children[i].data == "else_if" or node.children[i].data == "else":
                else_branch = node.children[i]
                break
            self.compile_statement(node.children[i])
        self.current_object.write_source("    }\n")
        
        if else_branch != None:
            self.compile_statement(else_branch)

    def compile_else(self, node):
        self.current_object.write_source("else {\n")

        for child in node.children:
            self.compile_statement(child)

        self.current_object.write_source("    }\n")

    def compile_else_if(self, node):
        self.current_object.write_source("else ")
        self.compile_if(node.children[0])

    def compile_while(self, node):
        self.current_object.write_source("while (")
        self.compile_expression(node.children[0])
        self.current_object.write_source("){\n")

        myself = self.while_counter
        self.while_counter += 1

        has_else = node.children[-1] != None and node.children[-1].data == "else"
        offset = 1 #if has_else else 0

        if has_else:
            self.break_labels.append("while_%s_else" % myself)
        else:
            self.break_labels.append(None)

        for i in range(1, len(node.children) - offset):
            self.compile_statement(node.children[i])

        self.current_object.write_source("    }\n")
        self.break_labels.pop()
        if has_else:
            self.current_object.write_source("    goto while_%s_end;\n" % myself)
            self.current_object.write_source("while_%s_else:\n" % myself)
            else_node = node.children[-1]
            for child in else_node.children:
                self.compile_statement(child)
            self.current_object.write_source("while_%s_end:\n" % myself)

    def compile_do_while(self, node):
        self.current_object.write_source("do {\n")
        self.break_labels.append(None)

        for i in range(0, len(node.children)-1):
            self.compile_statement(node.children[i])

        self.current_object.write_source("    } while(")
        self.compile_expression(node.children[-1])
        self.current_object.write_source(");\n")
        self.break_labels.pop()

    def compile_for(self, node):
        has_else = node.children[-1] != None and node.children[-1].data == "else"
        offset = 1 #if has_else else 0

        myself = self.for_counter
        self.for_counter += 1

        if has_else:
            self.break_labels.append("for_%s_else" % myself)
        else:
            self.break_labels.append(None)

        self.current_object.write_source("for(")
        if node.children[0] != None:
            self.compile_expression(node.children[0])
        self.current_object.write_source("; ")
        self.compile_expression(node.children[1])
        self.current_object.write_source("; ")
        if node.children[2] != None:
            self.compile_expression(node.children[2])
        self.current_object.write_source("){\n")

        for i in range(3, len(node.children) - offset):
            self.compile_statement(node.children[i])
        
        self.current_object.write_source("    }\n")
        self.break_labels.pop()

        if has_else:
            self.current_object.write_source("    goto for_%s_end;\n" % myself)
            self.current_object.write_source("for_%s_else:\n" % myself)
            else_node = node.children[-1]
            for child in else_node.children:
                self.compile_statement(child)
            self.current_object.write_source("for_%s_end:\n" % myself)

    def compile_break(self):
        if len(self.break_labels) == 0 or self.break_labels[-1] == None:
            self.current_object.write_source("break;\n")
        else:
            self.current_object.write_source("goto %s;\n" % self.break_labels[-1])

    def compile_continue(self):
        self.current_object.write_source("continue;\n")
    
    

with open("grammar.lark", "r") as f:
    Grammar = f.read()

errors = 0
def parser_error(e):
    global errors

    print("Error on line %s, col %s. Expected %s, got %s" % ( e.line, e.column, e.expected, e.token ))
    errors += 1
    return True

def main():
    global Grammar, errors
    code = ""

    file = "example.cal"
    if len(sys.argv) > 1:
        file = sys.argv[1]

    with open(file, "r") as f:
        code = f.read()

    parser = Lark(Grammar, parser="lalr", maybe_placeholders=True)
    parsed = parser.parse(code, on_error=parser_error)
    #print(parsed.pretty())

    if errors == 0:
        compiler = Compiler()
        compiler.compile(parsed, keep_source=True)
    else:
        print("Compilation aborted due to %s unresolved errors" % errors)


if __name__ == "__main__":
    main()

"""
Version 1.0
----------------------------
DONE: Finish Expressions (reference, derefrence, dereference+func_call)
DONE*: Branching Statements (if, for, while, break, continue)
DONE: Add Binary operators (both to the compiler + grammar)
TODO: Structs (struct + $struct{name, member} macro)
TODO: Add additional Macros (more refined macros) such as $sizeof $buffer $va_args $va_expand
TODO: Testing framework
TODO: Build System
TODO: Allow raw_c_statement at top level
TODO: Stdlib + Stdio + String + Math libraries
TODO: Error Unions and Handling
TODO: Better Compiler Error Handling
TODO: Switch/Match expression

Version 2.0
-----------------------------
TODO: Template functions (+ sizeof(type) sizeof(struct))
TODO: Refine syntax
TODO: Bug Fixes
TODO: Wide Pointers (better strings)
TODO: Anonymous Functions

Future Versions
-----------------------------
TODO: Capture Frames for Anonymous Functions (True Lambda)
TODO: Struct "." or "->" accessor syntax
TODO: Struct as type
TODO: Better Type Analysis for compile time

Known Bugs:
-----------------------------

"""
