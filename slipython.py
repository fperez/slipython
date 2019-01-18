#!/usr/bin/env python
"""SLIPython - Serverless IPython.
"""

# Stdlib imports
import sqlite3
import sys

# third party imports
try:
    import cloudpickle as pickle
except ImportError:
    import pickle

# IPython imports
from ipykernel.ipkernel import IPythonKernel


def serialize(obj):
    try:
        s = pickle.dumps(obj)
    except:
        s = f"Unserializable object <{repr(obj)[:50]}>"
    return s


def deserialize(s):
    try:
        obj = pickle.loads(s)
    except:
        obj = "<Unrecoverable Object>"
    return obj

# 

objects_sql = """\
CREATE TABLE IF NOT EXISTS objects (
    id integer PRIMARY KEY,
    object text
    );
"""

names_sql = """\
CREATE TABLE IF NOT EXISTS names (
    name text PRIMARY KEY,
    id integer,
    FOREIGN KEY (id) REFERENCES objects(id)
    );
    """


# Dbg - to get logging out to the screen for debugging... 
import logging

logging.basicConfig()
logger = logging.getLogger('SLIPython')
logger.setLevel(logging.DEBUG)


class NameSpaceStore:

    def __init__(self, ns, dbpath=":memory:"):
        self.ns = ns
        self.conn = sqlite3.connect(dbpath)
        self.cursor = self.conn.cursor()
        # Create tables
        self.cursor.execute(objects_sql)
        self.cursor.execute(names_sql)
        self.conn.commit()
        # Store vars
        seen = set()
        for varname, obj in self.ns.items():
            oid = id(obj)
            sys.stdout.flush()
            sn = "INSERT INTO names VALUES (?, ?)"
            self.cursor.execute(sn, (varname, oid))

            if oid in seen:
                continue
            else:
                #logger.info(f"*** Storing oid: {oid}")  # dbg
                so = "INSERT INTO objects VALUES (?, ?)"
                self.cursor.execute(so, (oid, serialize(obj)))
                seen.add(oid)
        self.conn.commit()

        # Initialize current list of variables
        self.current_vars = set(ns)


    def __del__(self):
        self.conn.close()


    def update_ns(self):
        """Update the managed namespace from persistent store."""

        # In the future, this should be driven by a code analysis so we only
        # pull in the variables we need, or those are pulled on demand through
        # a more finely instrumented VM so the backing store acts effectively
        # as (slower) memory.  For now, do a dumb pull from a db.


        # This is probably terrible db practice...
        cur = self.cursor

        with self.conn:
            s = """\
                SELECT name, object
                FROM names JOIN objects 
                WHERE names.id=objects.id
                """
            cur.execute(s)
            new_ns = {vname: deserialize(vs) 
                      for vname, vs in cur.fetchall()}
        self.ns.update(new_ns)
        logger.info("Updated ns with keys: %s", sorted(new_ns.keys()))


    def update(self):
        # Check user namespace for changes, save them..
        all_vars = set(self.ns)
        new_vars = all_vars - self.current_vars
        print(f"new vars: {new_vars}")  # dbg
        self.current_vars = all_vars


class SLIPKernel(IPythonKernel):
    # Kernel info fields
    implementation = 'Serverless IPython'
    implementation_version = '0.1'
    language_info = {
        'name': 'Serverless IPython',
        'version': sys.version.split()[0],
        'mimetype': 'text/x-python',
        'codemirror_mode': {
            'name': 'ipython',
            'version': sys.version_info[0]
        },
        'pygments_lexer': 'ipython3',
        'nbconvert_exporter': 'python',
        'file_extension': '.py'
    }

    banner = "Serverless IPython - a hack!!"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ns_store = NameSpaceStore(self.shell.user_ns)

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        
        #print("Keys:", list(self.shell.user_ns.keys())[:3]) # dbg

        self.ns_store.update_ns()
        out = super().do_execute(code, silent, store_history,
                                 user_expressions, allow_stdin)
        self.ns_store.update()
        return out


if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=SLIPKernel)
