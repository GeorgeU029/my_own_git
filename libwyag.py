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
    path = repo_file(repo,"obkects",sha[0:2],sha[2:]) 

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