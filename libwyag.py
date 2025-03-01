import argparse
import configparser
from datetime import datetime
import grp, pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

argparser = argparse.ArgumentParser(description="A script with subcommands.")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

argsp = argsubparsers.add_parser("init", help = "Initialize a new, empty repository.")
argsp.add_argument("path",
                   metavar = "directory",
                   nargs = "?",
                   default=".",
                   help="Where tp create the repository.")
argsp = argsubparsers.add_parser("cat-file",help="Provide content of repository object")
argsp.add_argument("type",
                   metavar="type",
                   choices=["blob","commit","tag","tree"],
                   help = "Specify the type")
argsp.add_argument("object",
                   metavar= "object",
                   help = "The object to display")
argsp = argsubparsers.add_parser(
    "hash-object",
    help = "Compute object ID and optionally creates a blob from a file")
argsp.add_argument("-t",
                   metavar="type",
                   dest="type",
                   choices=["blob","commit","tag","tree"],
                   default="blob",
                   help="Specify the Type")
argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object into the database")
argsp.add_argument("path",
                   help="Read object from <file>")
argsp = argsubparsers.add_parser("log", help = "Display history of a given commit.")
argsp.add_argument("commit",
                   default="HEAD",
                   nargs="?",
                   help="Commit to start at."
                   )
def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        case "add": cmd_add(args)
        case "cat-file": cmd_cat_file(args)
        case "check-ignore": cmd_check_ignore(args)
        case "checkout": cmd_checkout(args)
        case "commit": cmd_commit(args)
        case "hash-object": cmd_hash_object(args)
        case "init": cmd_init(args)
        case "log": cmd_log(args)
        case "ls-files": cmd_ls_files(args)
        case "ls-tree": cmd_ls_tree(args)
        case "rev-parse": cmd_rev_parse(args)
        case "rm": cmd_rm(args)
        case "show-ref": cmd_show_ref(args)
        case "status": cmd_status(args)
        case "tag": cmd_tag(args)
        case _: print("Bad command.")

class GitRepository(object):
    """A git repo"""

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git repository {path}")
        
        # Read config file in .git/config (fixed typo from .got/congfig)
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing") 

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatversion: {vers}")
class GitObject(object):

    def __init__(self,data=None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()
    def serialize(self,repo):
        """This function will be implemented by subclasses
        It will read the object's contents from self.data ,
        a byte string and do wtv it takes to convert it into a meaningful representaiton.
        This will be diff for each subclass. 
        """            
        raise Exception("Unimplemented!")
    def deserialize(self,data):
        raise Exception("Unimplemented!")
    def init(self):
        pass

def repo_path(repo, *path):
    """Compute path under repo's gitdir."""
    return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
    """Same as repo_path, but create dirname(*path) if absent. For example, 
    repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\")"""
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)

def repo_dir(repo, *path, mkdir=False):
    """Same as repo_path but mkdir *path if absent if mkdir."""
    path = repo_path(repo, *path)

    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        else:
            raise Exception(f"Not a directory {path}")
    
    if mkdir:
        os.makedirs(path)
        return path
    return None  # Fixed indentation and logic: return None if not mkdir

def repo_create(path):
    """Create a new repo at path."""
    repo = GitRepository(path, True)

    # First we make sure the path either does not exist or is an empty dir.
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory!")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)
    
    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)

    # .git/description
    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repo; edit this file 'description to name the repo.\n")
    # .git/HEAD
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")
    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)
    return repo

def repo_default_config():
    """Default configuration for a new repository."""
    ret = configparser.ConfigParser()
    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")
    return ret

def cmd_init(args):
    repo_create(args.path)
def repo_find(path=".",required = True):
    path = os.path.realpath(path)
    
    if os.path.isdir(os.path.join(path,".git")):
        return GitRepository(path)
    #If we have not retunred, recure in parent if w
    parent = os.path.realpath(os.path.join(path,".."))

    if parent == path:
        #Botoom case
        #os.path.join("/","..") == "/":
        #If parent==path,then path is root.
        if required:
            raise Exception("No git directory.")
        else:
            return None
        #recursive case
        return repo_find(parent,required)
def object_read(repo,sha):
    """Read object sha from git repo. Return a GitObject whose exact type depends on the object."""
    path = repo_file(repo,"objects",sha[0:2],sha[2:]) 

    if not os.path.isfile(path):
        return None
    with open (path, "rb") as f:
        raw = zlib.decompress(f.read())

        #read object type
        x = raw.find(b' ')
        fmt = raw[0:x]

        #read and validate object size
        y = raw.find(b'\x00',x)
        size = int(raw[x:y].decode("ascii"))
        if size != len(raw)-y-1:
            raise Exception(f"Malformed object {sha}: bad length")

        #Pick constructor
        match fmt:
            case b'commit' : c=GitCommit
            case b'tree' : c=GitTree
            case b'tag' : GitTag     
            case b'blob' : GitBlob
            case _:
                raise Exception(f"unknown type {fmt.decode("ascii")} for object {sha}")
            
        #call conts and return object
        return c(raw[y+1:])    
def object_write(obj, repo=None):
    #Serialize object data
    data = obj.serialize()    
    #adding the header
    result = obj.fmt + b' ' + str(len(data)).encode()+ b'\x00' + data
    #compute the hash 
    sha = hashlib.sha1(result).hexdigest()
    
    if repo:
        path = repo_file(repo,"objects",sha[0:2],sha[2:],mkdir=True)

        if not os.path.exists(path):
            with open(path, 'wb') as f:
                #Compress and write
                f.write(zlib.compress(result))
    return sha 

class GitBlob(GitObject):
    fmt=b'blob'

    def serialize(self):
        return self.blobdata
    def deserialize(self, data):
        self.blobdata = data
def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo,args.object,fmt=args.type.encode())
def cat_file(repo,obj,fmt=None):
    obj = object_read(repo,object_find(repo,obj,fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())
def object_find(repo,name,fmt=None,folllow=True):
    return name    
def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None
    with open(args.path, "rb") as fd:
        sha = object_hash(fd,args.type.encode(),repo)
        print(sha)   
def object_hash(fd,fmt,repo=None):
    """Hash object,writeting it to repo if provided."""             
    data = fd.read()

    #chose a constructor according to fmt argument
    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree' : obj=GitTree(data)
        case b'tag' : obj=GitTag(data)
        case b'blob' : obj=GitBlob(data)
        case _: raise Exception(f"Unknown type {fmt}!")

    return object_write(obj,repo)        
def kvlm_parse(raw,start = 0,dct = None):
    if not dct:
        dct = dict()
    spc = raw.find(b' ',start)
    nl = raw.find(b'\n',start)

    if (spc < 0) or (nl < spc):
        assert nl == start
        dct[None] = raw[start+1:]
        return dct
    key = raw[start:spc]

    end = start
    while True:
        end = raw.find(b'\n',end+1)
        if raw[end+1] != ord(' '): break

    value = raw[spc+1:end].replace(b'\n',b'\n')

    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [dct[key],value]
    else:
        dct[key] = value
    return kvlm_parse(raw,start=end+1,dct=dct)                                    

def kvlm_serialize(kvlm):
    ret = b''

    #output fiield
    for k in kvlm.keys():
        #skip the message itself
        if k == None: continue
        val = kvlm[k]

        if type(val) != list:
            val = [ val ]

        for v in val:
            ret += k + b' '+ (v.replace(b'\n',b'\n ')) + b'\n'
    
    #Append message
    ret += b'\n' + kvlm[None]
    return ret            
class GitCommit(GitObject):
    fmt =  b'commit'

    def deserialize(self,data):
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        return kvlm_serialize(self.kvlm)
    def init(self):
        self.kvlm = dict()        

def cmd_log(args):
    repo = repo_find()

    print("digraph wyag{")
    print(" node[shape=rect]")
    log_graphviz(repo,object_find(repo,args.commit),set())
    print("}")
def log_graphviz(repo,sha,seen):
    
    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo,sha)
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\","\\\\")
    message = message.replace("\"","\\\"")

    if "\n" in message:
        message = message[:message.index("\n")]
    printf(f" c_{sha} [label=\"{sha[0:7]}:{message}\"]")  
    assert commit.fmt==b'commit'

    if not b'parent' in commit.kvlm.keys():
        return
    parents = commit.kvlm[b'parent'] 

    if type(parents) != list:
        parents = [ parents ] 
    for p in parents:
        p = p.decode("ascii")
        print(f" c_{sha} -> c_{p};")
        log_graphviz(repo, p,seen)        

class GitTreeLeaf(object):   
    def __init__(self,mode,path,sha):
        self.mode = mode
        self.path = path
        self.sha = sha    

def tree_parse_one(raw,start = 0):
    #Find the space terminator of the mode
    x = raw.find(b' ',start)
    assert x-start == 5 or x-start == 6

    #read the mode
    mode = raw[start:x]
    if len(mode) == 5:
        #Normalize to six bytes.
        mode = b"0" + mode

    #Find the nULL terminator of the path
    y = raw.find(b'\x00',x)
    # and read the path
    path = raw[x + 1:y]    

    #read the SHA
    raw_sha =  int.from_bytes(raw [y+2:y+21], "big")
    #convert it into a hex string, padded to 40 chars
    #with zeros if needed.
    sha = format(raw_sha,"040x")
    return y+21,GitTreeLeaf(mode,path.decode("utf8"),sha)

def tree_parse(raw):
    pos =0
    max = len(raw)
    ret = list()
    
    while pos < max:
        pos, data = tree_parse_one(raw,pos)
        ret.append(data)
    return ret

def tree_leaf_sort_key(leaf):        
    if leaf.mode.startswith(b"10"):
        return leaf.path
    else:
        return leaf.path + "/"
def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)  
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha,16)
        ret += sha.to_bytes(20,byteorder="big")
    return ret                              

class GitTree(GitObject):
    fmt = b'tree'

    def deserialize(self,data):
        self.items = tree_parse(data)
    def serialize(self):
        return tree_serialize(self)
    def init(self):
        self.items = list()    