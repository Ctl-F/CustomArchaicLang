#!/usr/bin/env python3

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

class OutputTarget(Enum):
    Source = 0
    Header = 1
    PreDecl = 2

COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))

@dataclass
class ProjectInfo:
    name: str = ""
    project_dir: str = ""
    output_dir: str = ""
    flags: list = field(default_factory=lambda: [])
    search_paths: list = field(default_factory=lambda: [])
    required_links_for_proc_main: list = field(default_factory=lambda: [])

    def __init__(self, project_name, project_dir):
        self.name = project_name
        self.project_dir = project_dir
        self.search_paths = []
        self.flags = []
        self.required_links_for_proc_main = []
        self.dependancy_stack = []

        self.output_dir = "%s/bin/" % project_dir

        self.search_paths.append(os.path.join(project_dir, "src/"))
        self.search_paths.append(os.path.join(COMPILER_DIR, "libraries/"))

    def search_file(self, filename):
        for path in self.search_paths:
            name = os.path.join(path, filename)
            if os.path.exists(name):
                return name
        return ""

    def get_main_file(self):
        file = self.search_file(self.name + ".cal")
        if file == "":
            file = self.search_file("main.cal")
        return file
    
CurrentProject: ProjectInfo = None

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
        global CurrentProject
        name = self.get_name()
        self.target_header_name = "%s.h" % name
        self.target_source_name = "%s.c" % name

        CurrentProject.dependancy_stack.append(name)

    def get_local_func(self, name):
        for func in self.target_functions:
            if func["name"] == name:
                return func
        return None

    def export(self):
        global CurrentProject

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

        if self.target_type != ObjectType.Process:
            with open(os.path.join(CurrentProject.output_dir, self.target_header_name), "w") as f:
                f.write("".join(self.target_header_body))

        with open(os.path.join(CurrentProject.output_dir, self.target_source_name), "w") as f:
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

    def write(self, target, *what):
        match target:
            case OutputTarget.Source:
                self.write_source(*what)
            case OutputTarget.Header:
                self.write_header(*what)
            case OutputTarget.PreDecl:
                self.write_pre_decl(*what)

    def compile(self, **kwargs):
        global CurrentProject
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

        #if "target_dir" in kwargs:
        #    target_dir = kwargs["target_dir"]
        target_dir = CurrentProject.output_dir

        if not os.path.exists(target_dir):
            os.mkdir(target_dir)

        for link in CurrentProject.required_links_for_proc_main:
            if not link in self.target_link_objects:
                self.target_link_objects.append(link)

        links = ""
        for link in self.target_link_objects:
            links += "%slib%scal.o " % (target_dir, link)

        compile_only = "-c" if self.target_type == ObjectType.Library else ""

        command = "%s %s -o %s%s %s%s %s %s" % (compiler, compile_only, target_dir, object_name, target_dir, self.target_source_name, links, optimizations)
        print(command)
        os.system(command)
        CurrentProject.dependancy_stack.pop() # should be this

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
        self.error_sets = {}
        self.error_type = "int"
        self.error_type_name = "CAL_ERR_TY"
        self.error_structs = {}
        self.current_error_struct_type = None
        self.function_infos = {}
        self.error_index_counter = 0
        self.deferred_statements = []
        self.objects = []

    def compile(self, tree, **kw_args):
        self.compilation_args = kw_args

        if tree.data == "start":
            ls = sorted(tree.children, key=sort_objects)
            for item in ls:
                self.populate_function_infos(item)
        else:
            self.populate_function_infos(tree)

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

    def populate_function_infos(self, code_obj):
        if code_obj.data == "begin_lib":
            self.current_object = ObjectInfo(target_type=ObjectType.Library)
        elif code_obj.data == "begin_proc":
            self.current_object = ObjectInfo(target_type=ObjectType.Process)
        elif code_obj.data == "begin_test":
            pass
        
        self.current_object.target_name = str(code_obj.children[0])
        self.current_object.update_names()
        self.objects.append(self.current_object)

        if self.current_object.target_type != ObjectType.Process:
            self.current_object.write_header("#ifndef ", self.current_object.target_name, "_h\n#define ", self.current_object.target_name, "_h\n")
            self.current_object.write_pre_decl("#include \"", self.current_object.target_header_name, "\"\n\n")

        self.write_standard_headers()
        self.write_standard_defs()

        for item in code_obj.children[1].children:
            try:
                if item.data != "function":
                    continue
                self.get_function_info(item)
            except:
                continue
    
    def get_function_info(self, func_node):
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
            if func_node.children[cursor].startswith("$result"):
                return_type = str(func_node.children[cursor])
            else:
                return_type = self.get_c_type(str(func_node.children[cursor]))
            cursor += 1
        
        err_union_name = None

        if return_type.startswith("$result{"):
            ok_type = return_type[8:-1]
            if ok_type.find(".") == 0:
                ok_type = self.get_c_type(ok_type)
            else:
                ok_type = self.get_c_type("$struct{%s}" % ok_type)
        
            err_union_name = "_ERR_%s_OK_%s_TY" % (self.error_type_name, ok_type)

            if not (err_union_name in self.error_structs):
                self.generate_error_union(err_union_name, ok_type)

            return_type = "struct %s" % err_union_name

        glob_name = name
        if is_global:
            glob_name = "%s_%s" % (self.current_object.target_name, name)

        function_info = {
            "name": name,
            "global_name": glob_name,
            "params": params,
            "return_type": return_type,
            "is_global": is_global,
            "throws_err": return_type == ("struct %s" % err_union_name),
            "body_node": func_node.children[cursor]
        }
        self.function_infos[glob_name] = function_info
        self.function_infos[name] = function_info

    def write_standard_headers(self):
        target = OutputTarget.PreDecl if self.current_object.target_type == ObjectType.Process else OutputTarget.Header
        self.current_object.write(target, "\n#include <stdint.h>\n#include <stdbool.h>\n#include <stddef.h>\n\n")

    def write_standard_defs(self):
        target = OutputTarget.PreDecl if self.current_object.target_type == ObjectType.Process else OutputTarget.Header
        self.current_object.write(target, "#define %s %s\n" % (self.error_type_name, self.error_type))

    def reset_counters(self):
        self.while_counter = 0
        self.for_counter = 0
        self.error_index_counter = 0
        self.delta = 0

    def compile_lib(self, lib_node):
        self.reset_counters()

        name = lib_node.children[0]

        self.current_object = None
        for obj in self.objects:
            if obj.target_name == name:
                self.current_object = obj
                break
        
        if self.current_object == None:
            print("Error compiling lib, object not found")

        obj_name = self.current_object.get_name()
        print("Compiling library: %s" % obj_name)

        self.compile_code_unit(lib_node.children[1])

        self.current_object.export()
        self.current_object.compile(**self.compilation_args)

        print("done.")

    def compile_proc(self, proc_node):
        self.reset_counters()

        name = proc_node.children[0]

        self.current_object = None
        for obj in self.objects:
            if obj.target_name == name:
                self.current_object = obj
                break
        
        for object in self.objects:
            if object.target_type != ObjectType.Process:
                for link in object.target_link_objects:
                    self.current_object.target_link_objects.append(link)
        

        if self.current_object == None:
            print("Error compiling lib, object not found")

        obj_name = self.current_object.get_name()
        print("Compiling process: %s" % obj_name)

        # self.write_standard_headers()
        # self.write_standard_defs()

        self.compile_code_unit(proc_node.children[1])

        self.current_object.export()
        self.current_object.compile(**self.compilation_args)

        print("done.")

    def compile_test(self, test_node):
        pass

    def compile_struct_def(self, struct_node):
        is_global = struct_node.children[0] != None and str(struct_node.children[0]) == "glob"
        name = str(struct_node.children[1])

        target = OutputTarget.Header if is_global else OutputTarget.PreDecl

        visible_name = ("%s_%s" % (self.current_object.target_name, name)) if is_global else name
        
        self.current_object.write(target, "struct ", visible_name, "{\n" )

        for i in range(2, len(struct_node.children)):
            member_node = struct_node.children[i]
            c_type = self.get_c_type(str(member_node.children[0]))
            m_name = str(member_node.children[1])

            self.current_object.write(target, "    ", c_type, " ", m_name, ";\n")

        self.current_object.write(target, "};\n")

        if is_global:
            self.current_object.write_pre_decl("#define %s %s\n" % (name, visible_name))

    def compile_struct_member_macro(self, macro_node):
        name = str(macro_node.children[1])
        if macro_node.children[0] != None:
            name = "%s_%s" % (macro_node.children[0], name)
        self.current_object.write_source("offsetof(struct %s, %s)" % (name, macro_node.children[2]))


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
                case "raw_c_statement":
                    self.compile_inline_c(item)
                case "struct_def":
                    self.compile_struct_def(item)
                case "error_set":
                    self.compile_error_set(item)
                case _:
                    print("Error compiling code unit, unexpected item %s" % item)

            self.current_object.write_source("\n")

    def compile_link(self, link_node):
        global CurrentProject, Parser, errors
        for link in link_node.children:
            if link in CurrentProject.required_links_for_proc_main or link in CurrentProject.dependancy_stack:
                spoof = ObjectInfo(ObjectType.Library)
                spoof.target_name = str(link)
                spoof.update_names()

                self.current_object.target_link_objects.append(spoof.target_name)
                self.current_object.write_pre_decl("#include \"%s\"\n" % spoof.target_header_name)
            else:
                target_file = CurrentProject.search_file(link + ".cal")
                if target_file == "":
                    print("Link error on line %s, %s: Could not locate file '%s.cal' in provided search paths" % (link_node.meta.container_line, link_node.meta.container_column, link))
                    raise FileNotFoundError

                target_code = ""
                with open(target_file, "r") as f:
                    target_code = f.read()
                _errors = errors
                errors = 0
                parsed = Parser.parse(target_code, on_error=parser_error)

                if errors != 0:
                    print("Error compiling %s, aborting due to %s errors" % (target_file, errors))

                errors = _errors

                library_compiler = Compiler()
                library_compiler.compile(parsed)

                for obj in library_compiler.objects:
                    if not obj in self.objects:
                        self.objects.append(obj)

                    if not obj.target_name in CurrentProject.required_links_for_proc_main:
                        CurrentProject.required_links_for_proc_main.append(obj.target_name)
                        self.current_object.write_pre_decl("#include \"%s\"\n" % obj.target_header_name)

                for key, fdef in library_compiler.function_infos.items():
                    self.function_infos[key] = fdef
                
                pass

        

    def compile_c_include(self, c_include):
        self.current_object.write_source("#include <", str(c_include.children[0])[1:-1], ">\n")

    def generate_error_union(self, struct_name, ok_type):
        target = OutputTarget.Header

        if self.current_object.target_type == ObjectType.Process:
            target = OutputTarget.PreDecl

        self.current_object.write(target, "struct %s {\n" % struct_name)
        self.current_object.write(target, "    bool is_error;\n    union{\n")

        if ok_type == None or ok_type == "void":
            self.current_object.write(target, "    %s RESULT_ERROR;\n    int RESULT_OK;\n    };\n};\n\n" % (self.error_type_name))
        else:
            self.current_object.write(target, "    %s RESULT_ERROR;\n    %s RESULT_OK;\n    };\n};\n\n" % (self.error_type_name, ok_type))
        self.error_structs[struct_name] = 1

    def compile_function(self, func_node):
        cursor = 0
        is_global = False
        if func_node.children[cursor] == "glob":
            is_global = True
            cursor += 1
        name = str(func_node.children[cursor])

        if not name in self.function_infos:
            print("Problem with function infos")
            print("function %s not found" % name)
            print("line: %s, %s" % (func_node.meta.container_line, func_node.meta.container_column))
            raise NameError
        
        func_info = self.function_infos[name]
        is_global = func_info["is_global"]
        global_name = func_info["global_name"]
        params = func_info["params"]
        return_type = func_info["return_type"]
        body_node = func_info["body_node"]

        self.deferred_statements = []

        self.current_object.target_functions.append({ "name": name, "params": params, "returns": return_type, "is_global": is_global })

        if is_global:
            self.current_object.target_exported_functions.append( { "name": global_name, "params": params, "returns": return_type, "link": name })
        else:
            self.current_object.write_source("static ")

        self.current_object.write_source(return_type, " ", name, "(")

        i = 0
        for _ty, _name in params:
            self.current_object.write_source(_ty, " ", _name)
            if i + 1 < len(params):
                self.current_object.write_source(", ")
            i += 1

        self.current_object.write_source(")")

        if func_info["throws_err"]:
            self.current_error_struct_type = return_type

        self.compile_code_body(body_node)

        self.current_error_struct_type = None

    def get_c_type(self, type):
        if type.startswith("$struct{"):
            type = type[8:-1].strip()
            type = type.replace(".", "_")
            return "struct %s" % type

        """if type.starts_width("$result{"):
            internal_type = type[8:-1].strip()
            if internal_type.find(".") != -1:
                internal_type = self.get_c_type("$struct{%s}" % internal_type)
            else:
                internal_type = self.get_c_type(internal_type)"""
            
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
            case ".err":
                return self.error_type_name
            case _:
                print("Unknown type %s" % type)

    def get_params(self, params_list):
        params = []

        if params_list == None:
            return []

        is_va = params_list.children[-1] != None
        offset = 1

        for i in range(len(params_list.children)- offset ):
            param= params_list.children[i]
            type = self.get_c_type(str(param.children[0]))
            name = str(param.children[1])
            params.append((type, name))

        if is_va:
            params.append(("void*", "__VA_ARGS_BUF__"))
        
        return params

    def compile_statement(self, item):
        self.current_object.write_source("    ")
        try:
            match item.data:
                case "stack_allocation":
                    self.compile_stack_alloc(item)
                case "try_statement":
                    self.compile_try_statement(item)
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
                case "defer_statement":
                    self.compile_defer(item)

        except AttributeError:
            print("Error on line %s, %s: Unexpected item %s" % (item.meta.container_line, item.meta.container_column, item))

    def compile_defer(self, defer):
        self.deferred_statements.append(defer.children[0])

    def compile_error_set(self, error_set):
        set_name = str(error_set.children[0])
        target = OutputTarget.Header

        if self.current_object.target_type == ObjectType.Process:
            target = OutputTarget.PreDecl

        self.current_object.write(target, "///// BEGIN ERROR SET %s\n" % set_name)
        for i in range(1, len(error_set.children)):
            err_code = error_set.children[i]
            err_name = "%s_%s" % (set_name, err_code)
            self.current_object.write(target, "#define %s %s\n" % (err_name, self.error_index_counter))
            self.error_index_counter += 1

        self.current_object.write(target, "///// END ERROR SET %s\n\n" % set_name)

    def compile_try_statement(self, try_node):
        func_node = try_node.children[0]
        func_name = str(func_node.children[0].children[1])
        if func_node.children[0].children[0] != None:
            func_name = "%s_%s" % (func_node.children[0].children[0], func_name)
        
        if not func_name in self.function_infos:
            print("Error on line %s, %s: Try statement was used on a function that does not return a result type" % (try_node.meta.container_line, try_node.meta.container_column))
            raise LookupError

        func_info = self.function_infos[func_name]

        result_name = "_RESULT_%s" % self.delta
        self.delta += 1

        self.current_object.write_source("%s %s = " % (func_info["return_type"], result_name))

        self.compile_expression(func_node)
        self.current_object.write_source(";\n    ")

        self.current_object.write_source("if(!%s.is_error){\n" % result_name)
        cursor = 1

        if try_node.children[cursor] != None:

            ok_type = self.get_c_type(str(try_node.children[cursor]))
            cursor += 1
            ok_name = str(try_node.children[cursor])
            cursor += 1

            self.current_object.write_source("    %s %s = %s.RESULT_OK;\n" % (ok_type, ok_name, result_name))
            
            for i in range(cursor, len(try_node.children)-1):
                if try_node.children[i] == None:
                    continue
                self.compile_statement(try_node.children[i])
            
        self.current_object.write_source("    } else {\n    ")
        catch_node = try_node.children[-1]
        self.current_object.write_source("%s %s = %s.RESULT_ERROR;\n" % (self.error_type_name, catch_node.children[0], result_name))

        for i in range(1, len(catch_node.children)):
            self.compile_statement(catch_node.children[i])

        self.current_object.write_source("    } //END TRY/CATCH STMT\n")


    def compile_code_body(self, body_node):
        self.current_object.write_source("{\n")

        for item in body_node.children:
            self.compile_statement(item)


        self.expand_defers()
        self.current_object.write_source("}\n\n")

    def expand_defers(self):
        if len(self.deferred_statements) > 0:
            defers = reversed(self.deferred_statements)
            for defer in defers:
                self.compile_statement(defer)

    def compile_return(self, return_node):
        self.expand_defers()

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
            case "struct_member_offset":
                self.compile_struct_member_macro(expr)
            case "va_arg":
                self.compile_va_arg(expr)
            case "ok_result":
                self.compile_ok_result(expr)
            case "err_result":
                self.compile_err_result(expr)
            case "argument_list":
                for idx in range(len(expr.children) - 1):
                    child = expr.children[idx]
                    self.compile_expression(child)
                    if idx+1 < len(expr.children) - 1:
                        self.current_object.write_source(", ")
                #compile va_args...

    def compile_ok_result(self, expr):
        self.current_object.write_source("(%s){ .is_error = 0, .RESULT_OK = " % self.current_error_struct_type)
        if expr.children[0] != None:
            self.compile_expression(expr.children[0])
        else:
            self.current_object.write_source("0")
        self.current_object.write_source("}")

    def compile_err_result(self, expr):
        errcode_name = "%s_%s" % (expr.children[0], expr.children[1])
        self.current_object.write_source("(%s){ .is_error = 1, .RESULT_ERROR = %s }" % (self.current_error_struct_type, errcode_name))

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

    def compile_va_arg(self, node):
        pass

    def compile_func_call(self, node):
        if len(node.children) > 1 and node.children[1].children[-1] != None:
            #variadic function call
            va_node = node.children[1].children[-1]
            pass # the current way that we planned for va_args
            # to be handled is flawed. If we pass in expressions
            # then the original sizeof() could undesired second 
            # calls, and if we're calling a variadic function
            # in the middle of an expression then we'd start 
            # writing the buffer also in the middle of the expression
            # causing invalid C.
            # We either have to think of a new way, or start keeping
            # track of symbol types and write an equation type solver
            # Even if we do that we still have to resolve the buffer
            # creation code location. Either way this isn't as easy
            # of a feature as expected and other features may need to
            # be considered first with this one of the backburner.
            # Recommended Next: Error Unions and Catching, Testing + Build System

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
    

with open("./data/grammar.lark", "r") as f:
    Grammar = f.read()

errors = 0
current_file = ""
def parser_error(e):
    global errors, current_file

    print("%s) Error on line %s, col %s. Expected %s, got %s" % (current_file, e.line, e.column, e.expected, e.token ))
    errors += 1
    return True

def print_help():
    print("cal --help - prints help")
    print("cal init [name] { flags } -> initializes project")
    print("cal build [name] { flags } -> builds project")
    print("flags:")
    print("    -k  keep intermediate (.c/.h) files")
    print("    -r  compile in release mode (optimizations)")

def update_project(name):
    import shutil

    for root, dirs, files in os.walk("./libraries/"):
        for file in files:
            shutil.copy(os.path.join(root, file), os.path.join("./projects/%s/src" % name, file))

def init_project(name):
    os.mkdir("./projects/%s" % name)
    os.mkdir("./projects/%s/bin" % name)
    os.mkdir("./projects/%s/src" % name)
    
    #update_project(name)

    with open("./projects/%s/src/core.cal" % name, "w") as f:
        f.write("lib %s_core {\n" % name)
        f.write("    link stdio;\n\n")
        f.write("    glob fn hello(){\n")
        f.write("        stack .cstr message = \"Hello World\\n\";\n")
        f.write("        stdio.Print(message);\n")
        f.write("    }\n")
        f.write("}\n")

    with open("./projects/%s/src/main.cal" % name, "w") as f:
        f.write("proc %s {\n" % name)
        f.write("    link %s_core;\n\n" % name)
        f.write("    glob fn main(.i32 argc, .ptr_ptr argv) .i32 {\n")
        f.write("        %s_core.hello();\n" % name)
        f.write("    }\n")
        f.write("}\n")


def main():
    global Grammar, CurrentProject, errors, current_file, Parser
    code = ""

    #_t = sys.argv[0]
    #sys.argv = [_t, "build", "hello_world"]

    file = ""
    if len(sys.argv) <= 1 or sys.argv[0] == "--help":
        print_help()
        return

    command = sys.argv[1]

    if len(sys.argv) < 3:
        print("Please provide a project name")
        return
    
    name = sys.argv[2]

    flags = []

    for i in range(3, len(sys.argv)):
        flags.append(sys.argv[i])

    if not command in [ "build", "init", "update" ]:
        print("Unknown command %s" % command)
        return
    
    if command == "init":
        init_project(name)
        return
    
    if command == "update":
        update_project(name)
        return
    
    CurrentProject = ProjectInfo(name, "./projects/%s/" % name)
    file = CurrentProject.get_main_file()
    
    Parser = Lark(Grammar, parser="lalr", maybe_placeholders=True, propagate_positions=True)

    with open(file, "r") as f:
        code = f.read()
    current_file = file
    parsed = Parser.parse(code, on_error=parser_error)

    if errors == 0:
        compiler = Compiler()
        compiler.compile(parsed, keep_source=True)

        for object in compiler.objects:
            if os.path.exists(object.target_source_name):
                os.remove(object.target_source_name)
            if os.path.exists(object.target_header_name):
                os.remove(object.target_header_name)
    else:
        print("Compilation aborted due to %s unresolved errors" % errors)


if __name__ == "__main__":
    main()

"""
Version 1.0
----------------------------
DONE: Variables
DONE: Function Creation
DONE: Proc + Lib Creation
DONE: Proc Linking
DONE: Inline C
DONE: Compile C Output
DONE: Finish Expressions (reference, derefrence, dereference+func_call)
DONE*: Branching Statements (if, for, while, break, continue)
DONE: Add Binary operators (both to the compiler + grammar)
DONE: Structs (struct + $struct{name, member} macro)
DONE: Allow raw_c_statement at top level
DONE: Error Unions and Handling
DONE: Error Unions with Optional OK block
DONE*: Defer
DONE: Build System
TODO: Link to C Libraries 
TODO: $ifdebug{} else {} macro
TODO: Stdlib + Stdio + String + Math libraries
TODO: Testing framework
TODO: Better Compiler Error Handling
TODO: Switch/Match expression
TODO*: Add additional Macros (more refined macros) such as $sizeof $buffer $va_args $va_expand

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
