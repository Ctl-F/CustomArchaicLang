from lark import Lark, Transformer, v_args


class Compiler(Transformer):
    def __init__(self):
        self.exported_functions = []
        self.imported_functions = []
        self.header_file_body = []
        self.source_file_body = []
        self.object_name = ""
        self.object_type = ""

    @v_args(inline=True)
    def lib_unit(self, name, body):
        self.finish_obj()

        self.object_name = name
        self.object_type = 'L'

        name = self.get_name()
        name_upper = name.upper()

        self.header_file_body.append("#ifndef __%s__\n" % name_upper)
        self.header_file_body.append("#define __%s__\n" % name_upper)

        self.source_file_body.append('#include "%s.h"\n' % name)

    def finish_obj(self):
        if self.object_name != "":
            return
        
        name = self.get_name()

        with open("%s.h" % name, "w") as f:
            f.write("".join(self.header_file_body))
        
        with open("%s.c" % name, "w") as f:
            f.write("".join(self.source_file_body))

        self.object_name = ""
        self.imported_functions = ""
        self.exported_functions = ""
        self.header_file_body = []
        self.source_file_body = []
        self.object_type = ""

    def get_name(self):
        match self.object_type:
            case 'L':
                return "calib%s" % self.object_name
            case 'P':
                return self.object_name
            case 'T':
                return "test%s" % self.object_name
        return ""


with open("grammar.ebnf", "r") as f:
    Grammar = f.read()

def main():
    global Grammar
    code = ""
    with open("example.cal", "r") as f:
        code = f.read()

    parser = Lark(Grammar, parser="lalr", transformer=Compiler)
    parsed = parser.parse(code)
    print(parsed)


if __name__ == "__main__":
    main()
