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
ECM_DTE_PROMPT = 'root@ecm>'
LINUX_PROMPT = "~ # "
CLI_PROMPT = 'admin@FSP3000C> '
DBG_PROMPT = 'debug@FSP3000C> '
SSH_TIMEOUT = 5

class F8BrowserGUI:
    def __init__(self, master):

        #1: Create a builder
        self.builder = builder = pygubu.Builder()

        #2: Load an ui file
        builder.add_from_file('f8browser.ui')
  
        #3: Create the widget using a master as parent
        self.mainwindow = builder.get_object('mainWindow', master)
        self.master=master
        master.title("F8 Browser")
        master.iconbitmap(CURRENT_DIR+"\\"+"index.ico")
        self.newIPAddr = builder.tkvariables.__getitem__('newIPAddr')

        shelfTree = self.shelfTree = builder.get_object('shelfTree')        
        self.treeScroll = builder.get_object('shelfTreeScroll')
        self.shelfTree.configure(yscrollcommand=self.treeScroll.set)
        self.treeScroll.configure(command=self.shelfTree.yview)
        master.bind("<Button-3>",self.popup)
        master.bind("<Return>",self.onAddrAdded)
        self.guiThreads = []

        with open(CURRENT_DIR+CONFIG_JSON) as f:
            self.configDict = json.load(f)

        shelfTree['columns'] = ('slot','cuhi','ipv6','port')
        shelfTree.column('port', width=40, anchor='center')
        shelfTree.column('slot', width=40, anchor='center')
        shelfTree.column('cuhi', width=40, anchor='center')
        shelfTree.column('ipv6', width=200, anchor='center')
        shelfTree.column('#0', width=150, anchor='center')
        shelfTree.heading('port',text='Port',anchor='center')
        shelfTree.heading('slot',text='Slot',anchor='center')
        shelfTree.heading('cuhi',text='CUHI',anchor='center')
        shelfTree.heading('ipv6',text='IPV6',anchor='center')
        shelfTree.heading('#0',text='Name',anchor='center')
        for ip in self.configDict['knownShelfIP']:
            self.addNode(ip)
            
        shelfTree.bind("<<TreeviewOpen>>",self.onTreeviewOpened)
        self.ssh=None
        
        self.selectedId = ""
        
        self.slotPopup = builder.get_object('slotPopup')
        self.shelfPopup = builder.get_object('shelfPopup')
        self.portSub = builder.get_object('portSub')
        self.debugPortSub = builder.get_object('debugPortSub')
        webbrowser.register('firefox',None,webbrowser.BackgroundBrowser(self.configDict["Web Browsers"]["Firefox"]["Path"]))

        builder.connect_callbacks(self)
        
    def ssh_spawn(self,ip,username,port,password=""):
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
        if not self.selectedId:
            return
        shelfTree=self.shelfTree
        if shelfTree.parent(self.selectedId):
            slotid = self.selectedId
            nodeid = shelfTree.parent(slotid)
            slot= shelfTree.item(slotid)['values'][0]
            ipv6= shelfTree.item(slotid)['values'][2]
            port = slot+1000
        else:
            nodeid = self.selectedId
            if objID=="sshToDebug":
                port=SSH_DBG
            else:
                port=SSH_CLI
        shelfip = shelfTree.item(nodeid)['text']
   
        if objID=="deleteNode":
            shelfTree.delete(nodeid)
            self.configDict['knownShelfIP'].remove(shelfip)
            self.saveConfig()
            return
            
        if objID =="delPort":
            self.delPortForward(shelfip,port,slotid)
            return
        
        if objID=="httpToGui":
            wb=webbrowser.get(self.configDict["Web Browsers"]["Firefox"]["Path"])
            wb.open_new_tab(shelfip)
            return
            
        if objID=="enableDebug":
            self.enableDebug(shelfip,nodeid)
            return
        
        if port > 1000:
            self.addPortForward(shelfip,port,ipv6,slotid)
            
        if objID == "addPort": return
        
        if objID[:3]=="ssh":
            path=self.configDict["SSH Clients"]["Putty"]["Path"]
            if objID == "sshToCli":
                subprocess.Popen([path,"-ssh","-P",str(port),"admin@"+shelfip,"-pw","CHGME.1a"])
            else:
                subprocess.Popen([path,"-ssh","-P",str(port),"root@"+shelfip])
            
        elif objID[:3]=="scp":
            path=self.configDict["SCP Clients"]["WinSCP"]["Path"]
            subprocess.Popen([path,"root@"+shelfip+":"+str(port)])#+"/opt/adva/aos/lib/firmware/"])
            
        elif objID == "dteGui":
            self.guiThreads.append(None)
            self.spawn_gui(self.guiThreads[-1],guiThread,shelfip,slot,ipv6,LIB_DIR+"qflex.json")
        
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
        script = ["execute debug-system exec-cmd cmd \“/shell/enable-ssh\”",
                  "execute debug-system exec-cmd cmd \“/shell/enable-ssh\”",
                  "execute debug-system exec-cmd cmd \“/shell/cleanup\”"]
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
            if modName[:3] != "ECM":
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
        
    def spawn_gui(self,var,gui_thread,ipaddr,slot,ipv6,json_file):
        if var!=None and var.isAlive()==True:
            return
        var = gui_thread(self,ipaddr,slot,ipv6,json_file)
        var.start()
    
    def gui_handler(self,ipaddr,slot,ipv6,json_file):
        top=tk.Toplevel(self.master)
        gui = dg.dtegui(top,ipaddr,slot,ipv6,json_file)
        
    def popup(self,event):
        iid = self.shelfTree.identify_row(event.y)
        if iid:
            self.selectedId = iid
            self.shelfTree.selection_set(iid)
            if self.shelfTree.parent(iid):
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
                    
    def isOpen(self,ip,port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect((ip, int(port)))
            s.shutdown(2)
            return True
        except:
            return False
 
class guiThread (threading.Thread):
    def __init__(self,app,ipaddr,slot,ipv6,json_file):
        threading.Thread.__init__(self)
        self.app = app
        self.ipaddr=ipaddr
        self.slot=slot
        self.ipv6=ipv6
        self.json_file=json_file
    def run(self):
        self.app.gui_handler(self.ipaddr,self.slot,self.ipv6,self.json_file)  

if __name__ == '__main__':
    root = tk.Tk()
    f8b = F8BrowserGUI(root)
    root.mainloop()
    os._exit(0)