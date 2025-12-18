"""
ADB Handler Module for Line Ranger ID Store
Uses pure-python-adb (ppadb) for reliable ADB communication
Resolution: 960x540
Features:
- XML file transfer
- UI automation
- Screen overlay status
- Screenshot verification
- OCR for 2FA
"""
import time
import os
import re
from ppadb.client import Client as AdbClient
from config import Config

# Try to import OCR tools
try:
    from PIL import Image
    import pytesseract
    # Configure Tesseract path (Update if installed differently)
    # Default location for Windows
    tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("[ADB] Warning: PIL or pytesseract not installed. OCR features disabled.")

class ADBHandler:
    def __init__(self):
        self.adb_host = "127.0.0.1"
        self.adb_port = 5037
        self.emulator_ports = [7555, 5555, 16384, 62001, 21503]
        self.adb_path = Config.ADB_PATH
        self.package_name = Config.PACKAGE_NAME
        self.target_path = Config.TARGET_PATH
        self.target_filename = Config.TARGET_FILENAME
        self.device = None
        self.current_step = 0
        self.total_steps = 0
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), 'screenshots')
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.status_callback = None

    def set_callback(self, callback):
        self.status_callback = callback
    
    def start_adb_server(self):
        """Start ADB server"""
        print(f"[ADB] Starting server...")
        if os.path.exists(self.adb_path):
            os.system(f'"{self.adb_path}" start-server')
        else:
            os.system("adb start-server")
        time.sleep(2)
    
    def connect(self):
        """Connect to emulator"""
        self.start_adb_server()
        
        try:
            client = AdbClient(host=self.adb_host, port=self.adb_port)
            devices = client.devices()
            
            if len(devices) == 0:
                print(f"[ADB] Trying ports: {self.emulator_ports}")
                for port in self.emulator_ports:
                    try:
                        client.remote_connect("127.0.0.1", port)
                    except:
                        pass
                devices = client.devices()
            
            if len(devices) == 0:
                return {'success': False, 'error': 'No devices. Please open MuMu Player.'}
            
            self.device = devices[0]
            print(f"[ADB] Connected: {self.device.serial}")
            return {'success': True, 'message': f'Connected to {self.device.serial}'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def check_connection(self):
        if self.device:
            return {'success': True}
        return self.connect()
    
    # ==================== SHELL ====================
    
    def shell(self, command):
        if not self.device:
            self.connect()
        if self.device:
            return {'success': True, 'output': self.device.shell(command)}
        return {'success': False, 'error': 'No device'}
    
    def shell_su(self, command):
        return self.shell(f"su -c '{command}'")
    
    # ==================== OVERLAY & STATUS ====================
    
    def show_status(self, message, step=None):
        if step:
            self.current_step = step
        
        status_text = f"[{self.current_step}/{self.total_steps}] {message}"
        print(f"  📍 {status_text}")
        
        # Trigger callback if set
        if self.status_callback:
            try:
                self.status_callback(status_text)
            except Exception as e:
                print(f"Callback error: {e}")
                
        try:
            escaped = status_text.replace("'", "\\'").replace('"', '\\"')
            self.device.shell(f"cmd notification post -S bigtext -t 'LinkID' 'status' '{escaped}'")
        except:
            pass
        return status_text
    
    def set_total_steps(self, total):
        self.total_steps = total
        self.current_step = 0
        
    # ==================== OCR & SCREENSHOT ====================
    
    def screenshot(self, filename=None):
        """Capture screenshot"""
        if not self.device:
            self.connect()
        if filename is None:
            filename = f"screen_{int(time.time())}.png"
            
        device_path = "/sdcard/screenshot.png"
        local_path = os.path.join(self.screenshot_dir, filename)
        
        try:
            self.device.shell(f"screencap -p {device_path}")
            self.device.pull(device_path, local_path)
            self.device.shell(f"rm {device_path}")
            return local_path
        except:
            return None

    def read_verification_code(self):
        """
        Capture screen and use OCR to find numbers in the top-middle area
        Returns: String of digits found, or None
        """
        if not HAS_OCR:
            print("[OCR] Library not installed")
            return None
            
        print("[OCR] Capturing screen for 2FA code...")
        img_path = self.screenshot("2fa_check.png")
        if not img_path:
            return None
            
        try:
            img = Image.open(img_path)
            # Crop middle-top area (Left, Top, Right, Bottom)
            # Resolution: 960x540
            # Area: x=300-660, y=50-250 (Top middle)
            roi = img.crop((300, 50, 660, 250))
            
            # Use OCR to read digits
            text = pytesseract.image_to_string(roi, config='--psm 6 digits')
            digits = re.findall(r'\d+', text)
            
            if digits:
                code = "".join(digits)
                print(f"[OCR] Found code: {code}")
                # Save cropped image for debugging
                roi.save(os.path.join(self.screenshot_dir, f"roi_{code}.png"))
                return code
            else:
                print("[OCR] No digits found")
                return None
                
        except Exception as e:
            print(f"[OCR] Error: {e}")
            return None
    
    # ==================== FILE TRANSFER ====================
    
    def transfer_xml(self, source_xml_path):
        """Transfer XML to game's shared_prefs"""
        if not self.device:
            conn = self.connect()
            if not conn['success']:
                return conn
        
        if not os.path.exists(source_xml_path):
            return {'success': False, 'error': f'File not found: {source_xml_path}'}
        
        self.show_status("กำลังโอนไฟล์ XML...", 1)
        
        try:
            self.device.shell(f"am force-stop {self.package_name}")
            time.sleep(1)
            
            temp_path = f"/sdcard/{self.target_filename}"
            self.show_status("อัพโหลดไฟล์...")
            self.device.push(source_xml_path, temp_path)
            
            self.show_status("ย้ายไฟล์ด้วย root...")
            self.device.shell(f"su -c 'rm -f {self.target_path}'")
            self.device.shell(f"su -c 'mv {temp_path} {self.target_path}'")
            
            self.device.shell(f"su -c 'chmod 777 {self.target_path}'")
            
            self.show_status("โอนไฟล์สำเร็จ! ✓")
            return {'success': True, 'message': 'XML transferred'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== APP CONTROL ====================
    
    def force_stop_app(self):
        return self.shell(f"am force-stop {self.package_name}")
    
    def start_app(self):
        return self.shell(f"monkey -p {self.package_name} -c android.intent.category.LAUNCHER 1")
    
    def restart_app(self):
        self.force_stop_app()
        time.sleep(1)
        return self.start_app()
    
    # ==================== UI AUTOMATION ====================
    
    def tap(self, x, y, delay=1.0):
        self.device.shell(f"input tap {x} {y}")
        time.sleep(delay)
    
    def text_input(self, text, delay=0.5):
        escaped = text.replace(" ", "%s").replace("'", r"\'").replace("@", r"\@")
        self.device.shell(f"input text '{escaped}'")
        time.sleep(delay)
    
    def keyevent(self, keycode, delay=0.2):
        self.device.shell(f"input keyevent {keycode}")
        time.sleep(delay)
    
    def back(self, delay=0.3):
        self.keyevent(4, delay)
    
    def page_down(self, delay=0.5):
        self.keyevent(93, delay)
    
    def enable_touches(self):
        self.device.shell("settings put system show_touches 1")
        self.device.shell("settings put system pointer_location 1")
    
    def disable_touches(self):
        self.device.shell("settings put system show_touches 0")
        self.device.shell("settings put system pointer_location 0")
    
    # ==================== GAME AUTOMATION (960x540) ====================
    
    def automate_login(self, link_method, customer_id, customer_pass):
        """Full automation flow"""
        if not self.device:
            conn = self.connect()
            if not conn['success']:
                return conn
        
        if link_method.lower() == 'google':
            self.set_total_steps(15)
        else:
            self.set_total_steps(12)
        
        print("\n" + "="*50)
        print("[Automation] Starting... (960x540)")
        print("="*50)
        
        self.enable_touches()
        
        # Step 1: Wait for game
        self.show_status("รอเกมโหลด (30วิ)...", 1)
        time.sleep(30)
        
        # Step 2: Close check-in popup
        self.show_status("ปิด Check-in popup...", 2)
        self.tap(814, 62, delay=1.5)
        self.tap(814, 62, delay=1.5)
        self.tap(814, 62, delay=1.5)
        self.tap(814, 62, delay=1.5)
        
        # Step 3: BACK to clear popups
        self.show_status("ปิด popup...", 3)
        for i in range(100):
            self.back(0.15)
        time.sleep(1)
        
        # Step 4: Cancel exit
        self.show_status("ยกเลิกออกจากเกม...", 4)
        self.tap(400, 380, delay=1.0)
        
        # Step 5: Settings
        self.show_status("เปิด Settings...", 5)
        self.tap(845, 500, delay=1.5)
        
        # Step 6: Account
        self.show_status("เลือก Account...", 6)
        self.tap(710, 90, delay=1.0)
        
        # Step 7: Connect
        self.show_status("กด Connect...", 7)
        self.tap(580, 345, delay=1.5)
        
        # Step 8+: Login
        if link_method.lower() == 'google':
            self.show_status("เลือก Google Login...", 8)
            return self._login_google(customer_id, customer_pass)
        else:
            self.show_status("เลือก LINE Login...", 8)
            return self._login_line(customer_id, customer_pass)
    
    def check_screen_text(self, target_text, crop_box=None):
        """Check if specific text exists on screen. Optional crop_box=(L,T,R,B)"""
        if not HAS_OCR:
            return False
            
        print(f"[OCR] Checking for text: '{target_text}'...")
        img_path = self.screenshot("check_text.png")
        if not img_path:
            return False
            
        try:
            img = Image.open(img_path)
            
            # Crop if requested
            if crop_box:
                img = img.crop(crop_box)
                # Save crop debug
                img.save(os.path.join(self.screenshot_dir, "check_text_crop.png"))
            
            # Read full text
            text = pytesseract.image_to_string(img)
            print(f"[OCR] Found text: {text[:50]}...") # Print start of text
            
            if target_text.lower() in text.lower():
                return True
            return False
        except Exception as e:
            print(f"[OCR] Error: {e}")
            return False

    def _login_line(self, username, password):
        """LINE Login flow"""
        self.tap(480, 430, delay=2.0)
        
        self.show_status("กรอก LINE ID...", 9)
        self.tap(480, 315, delay=0.5)
        self.text_input(username)
        
        self.show_status("กรอก Password...", 10)
        self.tap(480, 420, delay=0.5)
        self.text_input(password)
        
        self.show_status("กด Login (รอ 8วิ)...", 11)
        self.tap(480, 530, delay=8.0)
        
        self.show_status("กด Allow & Consent...", 12)
        self.tap(480, 425, delay=2.0)
        self.tap(920, 215, delay=1.0)
        self.tap(920, 410, delay=1.0)
        self.tap(920, 520, delay=1.0)
        
        self.page_down(delay=1.0)
        self.tap(415, 405, delay=1.5)
        self.tap(480, 410, delay=1.0)
        
        # self.disable_touches() # Keep pointer strictly enabled as requested
        self.show_status("LINE Login สำเร็จ! ✓", 12)
        
        return {'success': True, 'message': 'LINE login complete'}
    
    def _login_google(self, username, password):
        """Google Login flow with Smart 2FA"""
        self.tap(480, 245, delay=3.0)
        
        self.show_status("กรอก Email...", 9)
        time.sleep(2)
        self.tap(430, 430, delay=0.5)
        self.text_input(username)
        
        self.show_status("กด Next...", 10)
        self.tap(860, 500, delay=3.0)
        
        self.show_status("กรอก Password...", 11)
        self.tap(400, 400, delay=0.5)
        self.text_input(password)
        
        self.show_status("กด Confirm...", 12)
        self.tap(860, 500, delay=5.0)
        
        # ⚠️ Smart 2FA Check
        self.show_status("ตรวจสอบ 2FA...", 13)
        time.sleep(3)
        
        # Crop header area (Google Logo + Title)
        # Adjusted by user: Cut Top 50%, Bottom 30% relative to previous
        # New Area: Focus strictly on "Verify it's you" text line
        header_crop = (200, 190, 760, 235)
        
        # Additional check for Footer "TRY ANOTHER WAY"
        # Area: Bottom Left (approx x:30-300, y:480-530 based on 960x540)
        footer_crop = (30, 480, 400, 540)
        
        is_2fa = (self.check_screen_text("Verify it's you", crop_box=header_crop) or 
                  self.check_screen_text("verify it's you", crop_box=header_crop) or 
                  self.check_screen_text("2-Step Verification", crop_box=header_crop) or
                  self.check_screen_text("TRY ANOTHER WAY", crop_box=footer_crop) or
                  self.check_screen_text("try another way", crop_box=footer_crop))
        
        verification_code = None
        message = "Google Login Success"
        
        if is_2fa:
            self.show_status("‼ พบหน้า 2FA: กด Spacebar...", 13)
            # Press Spacebar (Keycode 62)
            self.keyevent(62, delay=2.0)
            
            self.show_status("อ่านเลข 2 digits...", 13)
            # Re-use read_verification_code logic but focused
            img_path = self.screenshot("2fa_code.png")
            if img_path:
                try:
                    img = Image.open(img_path)
                    # Use tighter crop based on user feedback
                    # Original: (300, 50, 660, 300)
                    # New: Cut L/R 25%, Bottom 70% -> (390, 50, 570, 125)
                    roi = img.crop((390, 50, 570, 125))
                    
                    # --- Image Preprocessing for better OCR ---
                    # Convert to grayscale
                    roi = roi.convert('L') 
                    # Thresholding (Binarize) - make text black/white explicitly
                    threshold = 200
                    roi = roi.point(lambda p: p > threshold and 255) 
                    
                    # Save Debug Image
                    debug_name = f"debug_crop_{int(time.time())}.png"
                    roi.save(os.path.join(self.screenshot_dir, debug_name))
                    print(f"[OCR] Saved debug crop to: {debug_name}")
                    
                    # Read text
                    text = pytesseract.image_to_string(roi, config='--psm 6 digits')
                    digits = re.findall(r'\d+', text)
                    if digits:
                        code = "".join(digits)
                        # Filter to ensure reasonable length (now accepting 1 digit)
                        if len(code) >= 1: 
                            verification_code = code[:2] # Take first 1-2 digits
                            self.show_status(f"🔑 USER CODE: {verification_code}", 13)
                            message = f"Found 2FA Code: {verification_code}"
                except Exception as e:
                    print(f"Error reading 2FA: {e}")
            
            if not verification_code:
                self.show_status("❌ ไม่พบเลข 2 digits", 13)
                
        else:
            self.show_status("ไม่พบ 2FA -> ไปหน้า Consent", 13)
            # Consent steps only if NOT 2FA (as requested)
            self.show_status("Consent steps...", 14)
            self.page_down(delay=1.0)
            self.tap(825, 280, delay=1.5)
            self.tap(110, 495, delay=1.5)
            self.tap(810, 505, delay=1.5)
            self.tap(810, 505, delay=1.5)
            self.tap(70, 510, delay=1.5)
            self.tap(630, 440, delay=1.5)
            self.tap(555, 360, delay=1.0)
            self.tap(480, 410, delay=2.5)
            self.tap(920, 220, delay=1.0)
            self.tap(920, 415, delay=1.0)
            self.tap(920, 520, delay=1.0)
            self.page_down(delay=1.0)
            self.tap(415, 405, delay=1.0)
        
        # self.disable_touches()
        self.show_status("Google Login จบขั้นตอน! ✓", 15)
        
        return {
            'success': True, 
            'message': message,
            'verification_code': verification_code
        }


# Global instance
adb_handler = ADBHandler()


def link_id(source_xml_path, link_method=None, customer_id=None, customer_pass=None, automate=True, callback=None):
    """Main function"""
    print("\n" + "="*60)
    print("[Link ID] Starting process...")
    print("="*60)
    
    # Set callback
    if callback:
        adb_handler.set_callback(callback)
    
    conn = adb_handler.connect()
    if not conn['success']:
        return conn
    
    adb_handler.set_total_steps(3 if not automate else 15)
    
    adb_handler.show_status("เริ่มโอนไฟล์ XML...", 1)
    transfer = adb_handler.transfer_xml(source_xml_path)
    if not transfer['success']:
        return transfer
    
    adb_handler.show_status("เปิดเกม...", 2)
    adb_handler.start_app()
    
    result = {
        'success': True,
        'message': 'ID linked successfully!',
        'transfer': transfer
    }
    
    if automate and link_method and customer_id and customer_pass:
        adb_handler.show_status("เริ่ม Automation...", 3)
        auto_result = adb_handler.automate_login(link_method, customer_id, customer_pass)
        result['automation'] = auto_result
        
        # update message with verification code if found
        if auto_result.get('verification_code'):
             result['message'] = f"Google 2FA Code: {auto_result['verification_code']}"
             result['verification_code'] = auto_result['verification_code']
        else:
             result['message'] = f'ID linked and {link_method} login completed!'
    
    print("\n" + "="*60)
    print("[Link ID] ✓ Process complete!")
    print("="*60 + "\n")
    
    # Clear callback
    adb_handler.set_callback(None)
    
    return result


def continue_phase2(callback=None):
    """Phase 2 Automation: Executed after 2FA Confirmation"""
    print("\n" + "="*60)
    print("[Phase 2] Starting automation...")
    print("="*60)
    
    # Set callback locally if needed (though adb_handler is global)
    if callback:
        adb_handler.set_callback(callback)
    
    # Ensure connection
    if not adb_handler.device:
        conn = adb_handler.connect()
        if not conn['success']:
            return conn

    try:
        adb_handler.show_status("เริ่ม Phase 2...", 1)
        
        # 1. Arrow Down x30 (Replacing Page Down)
        # 20 = KEYCODE_DPAD_DOWN
        for _ in range(30):
            adb_handler.keyevent(20, delay=0.05)
        time.sleep(1.0)
        
        # 2. Tap (825, 285)
        adb_handler.tap(95, 415, delay=1.5)

        
        # 1. Arrow Down x30 (Replacing Page Down)
        # 20 = KEYCODE_DPAD_DOWN
        
        adb_handler.show_status("เลื่อนลง...", 9)
        for _ in range(30):
            adb_handler.keyevent(20, delay=0.05)
        time.sleep(1.0)

        adb_handler.show_status("กด Next...", 10)
        # 2. Tap (825, 285)
        adb_handler.tap(825, 285, delay=1.5)
        
        adb_handler.show_status("Tap Next...", 11)
        # 3. Tap (110, 490)
        adb_handler.tap(110, 490, delay=1.5)
        
        adb_handler.show_status("Tap Next...", 12)
        # 4. Tap (265, 490)
        adb_handler.tap(265, 490, delay=1.5)
        # 4. Tap (265, 490)
        adb_handler.tap(75, 490, delay=1.5)
        
        adb_handler.show_status("Tap Next...", 13)
        # 5. Tap (860, 505) x2
        adb_handler.tap(860, 505, delay=1.0)
        # 4. Tap (265, 490)
        adb_handler.tap(75, 490, delay=1.5)
        adb_handler.tap(860, 505, delay=1.5)
        # 4. Tap (265, 490)
        adb_handler.tap(75, 490, delay=1.5)
        
        adb_handler.show_status("Tap Next...", 14)
        # 6. Tap (485, 410)
        adb_handler.tap(485, 410, delay=1.5)
        # 4. Tap (265, 490)
        adb_handler.tap(75, 490, delay=1.5)
        
        adb_handler.show_status("Tap Next...", 15)
        # 7. Tap (920, 215)
        adb_handler.tap(920, 215, delay=1.0)
        
        adb_handler.show_status("Tap Next...", 16)
        # 8. Tap (920, 410)
        adb_handler.tap(920, 410, delay=1.0)
        
        adb_handler.show_status("Tap Next...", 17)
        # 9. Tap (920, 520)
        adb_handler.tap(920, 520, delay=1.0)
        
        adb_handler.show_status("Tap Next...", 18)
        # 10. Page Down x1
        adb_handler.page_down(delay=1.0)
        
        adb_handler.show_status("Tap Next...", 19)
        # 11. Tap (415, 405)
        adb_handler.tap(415, 405, delay=1.0)
        
        adb_handler.show_status("Phase 2 เสร็จสิ้น! ✓", 99)
        return {'success': True, 'message': 'Phase 2 complete'}
        
    except Exception as e:
        print(f"Phase 2 Error: {e}")
        return {'success': False, 'error': str(e)}


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 4:
        link_id(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif len(sys.argv) == 2:
        link_id(sys.argv[1], automate=False)
