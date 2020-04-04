import sshexpect
import tkinter as tk
from tkinter import messagebox
import pygubu
import os
import json
import dtegui as dg
import threading
import subprocess
import webbrowser
import ipaddress
import socket
import ctypes
import time
import click
from ctypes import wintypes
from pynput.keyboard import Key,Controller

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))+"\\"
LIB_DIR = CURRENT_DIR+"lib\\"
CONFIG_JSON = "config.json"
SSH_USERNAME = "root"
SSH_PASSWORD = ""
CLI_USERNAME = "admin"
DBG_USERNAME = "debug"
CLI_PASSWORD = "CHGME.1a"
SSH_DBG = 614
SSH_CLI = 22
ECM_DTE_PROMPT = ['root@ecm>','root@tecm>']
LINUX_PROMPT = "~ # "
CLI_PROMPT = 'admin@FSP3000C> '
DBG_PROMPT = 'debug@FSP3000C> '
SSH_TIMEOUT = 5

EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
IsWindowEnabled = ctypes.windll.user32.IsWindowEnabled
SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow

class F8BrowserGUI:
    def __init__(self, master,debug=False):

        #1: Create a builder
        self.builder = builder = pygubu.Builder()

        #2: Load an ui file
        builder.add_from_file(CURRENT_DIR+'f8browser.ui')
  
        #3: Create the widget using a master as parent
        self.mainwindow = builder.get_object('mainWindow', master)
        self.master=master
        master.title("F8 Browser")
        master.iconbitmap(LIB_DIR+"adva.ico")
        self.newIPAddr = builder.tkvariables.__getitem__('newIPAddr')
        #self.ahk = AHK()

        shelfTree = self.shelfTree = builder.get_object('shelfTree')        
        self.treeScroll = builder.get_object('shelfTreeScroll')
        shelfTree.configure(yscrollcommand=self.treeScroll.set)
        self.treeScroll.configure(command=self.shelfTree.yview)
        master.bind("<Button-3>",self.popup)
        master.bind("<Return>",self.onAddrAdded)
        self.guiThreads = []

        with open(CURRENT_DIR+CONFIG_JSON) as f:
            self.configDict = json.load(f)

        shelfTree['columns'] = ('slot','cuhi','ipv6','port')#,'group')
        #shelfTree.column('group', width=40, anchor='center')
        shelfTree.column('port', width=40, anchor='center')
        shelfTree.column('slot', width=40, anchor='center')
        shelfTree.column('cuhi', width=40, anchor='center')
        shelfTree.column('ipv6', width=200, anchor='center')
        shelfTree.column('#0', width=150, anchor='center')
        #shelfTree.heading('group',text='Group',anchor='center')
        shelfTree.heading('port',text='Port',anchor='center')
        shelfTree.heading('slot',text='Slot',anchor='center')
        shelfTree.heading('cuhi',text='CUHI',anchor='center')
        shelfTree.heading('ipv6',text='IPV6',anchor='center')
        shelfTree.heading('#0',text='Name',anchor='center')
        for ip in self.configDict['knownShelfIP']:
            self.addNode(ip)
            
        shelfTree.bind("<<TreeviewOpen>>",self.onTreeviewOpened)
        self.ssh=None
        
        self.selection = ()
        self.debug = debug
        self.slotPopup = builder.get_object('slotPopup')
        self.shelfPopup = builder.get_object('shelfPopup')
        self.portSub = builder.get_object('portSub')
        self.debugPortSub = builder.get_object('debugPortSub')
        
        self.keyboard = Controller()
        
        for browser in self.configDict["Web Browsers"]:  
            webbrowser.register(browser,None,webbrowser.BackgroundBrowser(self.configDict["Web Browsers"][browser]["Path"]))

        builder.connect_callbacks(self)
        
        self.groupDict = {}
        
    def ssh_spawn(self,ip,username,port,password=""):
        if self.debug: print("SSH spawn:",ip,username,port,password)
        try:
            ssh = sshexpect.spawn(ipaddress=ip,username=username,password=password,port=port,timeout=SSH_TIMEOUT)
        except:
            mb = messagebox.showerror(title='Error',message='Unable to open SSH session with {}.'.format(ip))
            return None
        return ssh
        
    def ssh_expect(self,ssh,prompt):
        try:
            ssh.expect(prompt)
        except:
            mb =  messagebox.showerror(title='Error',message='No response from SSH command.'%ip)
            ssh.close()
            raise Exception("Timeout in ssh_expect!")
        
    def ssh_expect_script(self,ssh,prompt,script):
        for line in script:
            ssh.sendln(line)
            try:
                self.ssh_expect(ssh,prompt)
            except:
                raise Exception("Timeout in ssh_expect_script!")
                return
        
    def validateIPAddr(self,ip):
        try:
            ipaddress.ip_address(ip)
        except:
            return False
        return self.isOpen(ip,SSH_CLI)
        
    def saveConfig(self):
        with open(CURRENT_DIR+CONFIG_JSON,'w') as f:
            json.dump(self.configDict, f, sort_keys=True, indent=4, separators=(',',':'))
        
    def onAddrAdded(self,event=None):
        ip=self.newIPAddr.get()
        if self.validateIPAddr(ip):
            self.configDict['knownShelfIP'].append(ip)
            self.saveConfig()
            self.addNode(ip)
            return
        mb = messagebox.showerror(title='Error',message='Invalid IP or SSH port not open.')
    
    def addNode(self,ip):
        for existing in self.shelfTree.get_children():
            if ip in self.shelfTree.item(existing,'text'):
                mb = messagebox.showerror(title='Error',message='IP already added.')
                return
        node=self.shelfTree.insert('','end', text=ip, open=False)
        if self.isOpen(ip,SSH_DBG):
            self.shelfTree.insert(node,'end',text="")
            self.shelfTree.set(node,'port',SSH_DBG)
        
    def eventHandler(self,objID):
        
        if not self.selection:
            return
           
        shelfTree=self.shelfTree
        configDict=self.configDict
        wb = None
        for item in self.selection:

            if self.hasParent(item):
                slotid = item
                nodeid = shelfTree.parent(slotid)
                slot= shelfTree.item(slotid)['values'][0]
                cuhi= shelfTree.item(slotid)['values'][1]
                ipv6= shelfTree.item(slotid)['values'][2]
                port = slot+1000
            else:
                nodeid = item
                slot = ""
                if objID=="sshToCli":
                    port=SSH_CLI
                else:
                    port=SSH_DBG
            shelfip = shelfTree.item(nodeid)['text']
    
            if objID=="deleteNode":
                shelfTree.delete(nodeid)
                configDict['knownShelfIP'].remove(shelfip)
                self.saveConfig()
                continue
                
            if objID =="delPort":
                self.delPortForward(shelfip,port,slotid)
                continue
            
            if objID=="httpToGui":
                browser = configDict["General"]["Browser"]
                if not wb:
                    wb=webbrowser.get(configDict["Web Browsers"][browser]["Path"])
                    time.sleep(1)
                wb.open_new_tab(shelfip)
                continue
                
            if objID=="enableDebug":
                self.enableDebug(shelfip,nodeid)
                continue
            
            if port > 1000:
                self.addPortForward(shelfip,port,ipv6,slotid)
                
            if objID == "addPort": continue
            
            if objID[:3]=="ssh":
                
                path=configDict["SSH Clients"]["Putty"]["Path"]
                if objID == "sshToCli":
                    pargs=[path,"-ssh","-P",str(port),"admin@"+shelfip,"-pw","CHGME.1a"]
                    title = shelfip + " - PuTTY"
                else:   
                    title = shelfip + " Slot "+str(slot)
                    pargs=[path,"-ssh","-P",str(port),"root@"+shelfip,"-loghost",title]
                    title = title + " - PuTTY"
                
                script = []
                if objID == "sshToDTE":
                    script = configDict["Scripts"]["Start DTE"]
                
                self.spawnWindowsProgram(pargs,title,script=script)
    
                continue
                
            if objID[:3]=="scp":
                path=configDict["SCP Clients"]["WinSCP"]["Path"]
                pargs=[path,"root@"+shelfip+":"+str(port),"/sessionname="+shelfip+" Slot "+str(slot)]
                
                self.spawnWindowsProgram(pargs,"WinSCP",delayAfterOpen=1)
                continue
                
            if objID == "dteGui":
                cuhi = str(shelfTree.item(slotid)['values'][1])
                if cuhi in configDict["GUI Config"].keys():
                    guiConfig=configDict["GUI Config"][cuhi]
                    top=tk.Toplevel(self.master)
                    dg.dtegui(top,shelfip,slot,cuhi,ipv6,LIB_DIR+guiConfig,debug=False)
                    continue
                mb = messagebox.showerror(title='Error',message='No GUI config for CUHI:{}.'.format(cuhi))
                continue
            mb = messagebox.showerror(title='Error',message='No action found for menu command!')
            return
        
    def spawnWindowsProgram(self,pargs,texpected,delayAfterOpen = 0.5,script=[]):
    
        p = subprocess.Popen(pargs)      
        time.sleep(delayAfterOpen)  
        h =  get_hwnds_for_pid (p.pid)           
        if h==[]: return False     
        t= get_title_for_hwnd(h[0])
       
        if not texpected in t:
            for timeout in range(60):
                time.sleep(0.5)
                h =  get_hwnds_for_pid (p.pid) 
                if h==[]: return False
                t= get_title_for_hwnd(h[0])
                if texpected in t:
                    time.sleep(delayAfterOpen)
                    break
            if timeout == 59:
                print ("Timeout waiting for user action on window!")
                return False
                
        if script != []:
            SetForegroundWindow(h[0])
            keytext = '\n'.join(script)+'\n'
            self.keyboard.type(keytext)
            
        return True 
        
    def addPortForward(self,shelfip,port,ipv6,slotid):
        try:
            ssh = self.ssh_spawn(shelfip,SSH_USERNAME,SSH_DBG)
            self.ssh_expect(ssh,LINUX_PROMPT)
            ssh.sendln("ssh -o StrictHostKeyChecking=no -g -L "+str(port)+":localhost:22 -f -N root@"+ipv6+"%mgmt")
            self.ssh_expect(ssh,LINUX_PROMPT)
            self.shelfTree.set(slotid,'port',str(port))
        except:
            return
        
    def enableDebug(self,ip,nodeid):
        script = configDict["Scripts"]["Enable Debug"]
        try:
            ssh = self.ssh_spawn(shelfip,CLI_USERNAME,SSH_CLI,password=CLI_PASSWORD)
            ssh.sendln("set security user debug role Debug new-password "+CLI_PASSWORD)
            self.ssh_expect(ssh,CLI_PROMPT)
            ssh.close()
            ssh = self.ssh_spawn(shelfip,DBG_USERNAME,SSH_CLI,password=CLI_PASSWORD)
            self.ssh_expect_script(ssh,DBG_PROMPT,script)
            ssh.close()
            self.shelfTree.set(nodeid,'port',SSH_DBG)
        except:
            return
        
    def getShelfTreeInfo(self,shelfip):
        try:
            ssh = self.ssh_spawn(shelfip,SSH_USERNAME,SSH_DBG)
            self.ssh_expect(ssh,LINUX_PROMPT)
            ssh.sendln("ps -x | grep -o \"10[0-9][0-9]:localhost:22\"")
            self.ssh_expect(ssh,LINUX_PROMPT)
            ports = []
            for line in ssh.before.splitlines():
                if "localhost"in line and not "ps -x" in line:
                    port = line.split(':')[0]
                    if not port in ports:
                        ports.append(port)
            ssh.sendln('aosCoreDteConsole')
            self.ssh_expect(ssh,ECM_DTE_PROMPT)
            ssh.sendln('/debug/aosCoreTd/getTopologyTree')
            self.ssh_expect(ssh,ECM_DTE_PROMPT)
            ssh.close()
            return ports,ssh.parsebefore(trigger="cuhi",location=[[1,0],[1,1],[1,4]],retrigger=True)
        except:
            raise Exception("Communication error during getShelfTreeInfo!")
        
    def onTreeviewOpened(self,event):
        node = self.shelfTree.selection()
        shelfip = self.shelfTree.item(node)['text']
        items = self.shelfTree.get_children(node)
        if self.debug: print("Treeview Opened:",node,shelfip,items)
        try:
            portlist,slotlist =self.getShelfTreeInfo(shelfip)
        except:
            return
        self.shelfTree.delete(*items)
        for slot in slotlist:
            modName='Unknown'
            if slot[0] in self.configDict['uhiLookup']:
                modName=self.configDict['uhiLookup'][slot[0]]
            port = str(int(slot[1]) + 1000)
            if not port in portlist:
                port = ""
            if not "ECM" in modName:
                self.shelfTree.insert(node,'end',text=modName,values=(slot[1],slot[0],slot[2],port))
                
    def delPortForward(self,shelfip,port,slotid):
        try:
            ssh = self.ssh_spawn(shelfip,SSH_USERNAME,port)
            self.ssh_expect(ssh,LINUX_PROMPT)
            ssh.sendln("pkill -f \""+str(port)+":localhost:22\"")
            self.ssh_expect(ssh,LINUX_PROMPT)
            ssh.close()
            self.shelfTree.set(slotid,'port',"")
        except:
            return
        
    def popup(self,event):
        iid = self.shelfTree.identify_row(event.y)
        if not iid: return
        selection = self.shelfTree.selection()
        if len(selection) <= 1 :
            self.shelfTree.selection_set(iid)
            selection = self.shelfTree.selection()
        else:
            compare = self.hasParent(selection[0])
            for idx in range(1,len(selection)):
                if self.hasParent(selection[idx])!=compare:
                    return
        self.selection = selection
        if self.hasParent(selection[0]):
            if self.shelfTree.item(iid)['values'][3] == "":
                self.portSub.entryconfig(1,state="disabled")
                self.portSub.entryconfig(0,state="normal")
            else:    
                self.portSub.entryconfig(1,state="normal")
                self.portSub.entryconfig(0,state="disabled")
            try:
                self.slotPopup.tk_popup(event.x_root, event.y_root, 0)
            finally:
                self.slotPopup.grab_release()
        else:
            if self.shelfTree.item(iid)['values'][3] == "":
                self.debugPortSub.entryconfig(0,state="normal")
            else:
                self.debugPortSub.entryconfig(0,state="disabled")
            try:
                self.shelfPopup.tk_popup(event.x_root, event.y_root, 0)
            finally:
                self.shelfPopup.grab_release()
                
    def hasParent(self,node):
        if not self.shelfTree.parent(node):
            return False
        return True
                    
    def isOpen(self,ip,port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect((ip, int(port)))
            s.shutdown(2)
            return True
        except:
            return False
        
def get_title_for_hwnd(hwnd):
    length = GetWindowTextLength(hwnd)+1
    title = ctypes.create_unicode_buffer(length)
    GetWindowText(hwnd,title,length)
    return title.value
      
def get_hwnds_for_pid (pid):
  hwnds = []
  def callback (hwnd, lParam):
    found_pid = ctypes.c_ulong()
    if IsWindowVisible (hwnd) and IsWindowEnabled (hwnd):
      result = ctypes.windll.user32.GetWindowThreadProcessId (hwnd, ctypes.byref(found_pid))
      if found_pid.value == pid:
        hwnds.append (hwnd)
    return True  
  EnumWindows (EnumWindowsProc(callback),0)
  return hwnds

@click.command()
@click.option('--debug',default=False)
def f8browserCli():
    root = tk.Tk()
    f8b = F8BrowserGUI(root,debug=debug)
    root.mainloop()
    os._exit(0)
    
if __name__ == "__main__":
    f8browserCli()