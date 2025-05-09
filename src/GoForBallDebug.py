import rospy
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from std_msgs.msg import Int32
import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
import time

class TurtlebotVisionController:
    def __init__(self):
        rospy.init_node("turtlebot_vision_controller", anonymous=True)

        # Initialize CvBridge
        self.bridge = CvBridge()

        # Subscribe to USB camera topic
        self.subscriber = rospy.Subscriber("/usb_cam/image_raw", Image, self.image_callback)

        # Publisher for velocity commands
        self.publisher = rospy.Publisher("/cmd_vel", Twist, queue_size=10)

        # Publisher for velocity commands
        self.image_publisher = rospy.Publisher("/ball_image", Image, queue_size=10)

        #Publisher for sound effects
        self.sound_publisher = rospy.Publisher("/sound_type", String, queue_size=10)

        #Publisher for explorer
        self.explorer_publisher = rospy.Publisher("/ball_status", Int32, queue_size=10)

        # Define movement speed
        self.forward_speed = 0.4
        self.minAngle = 0
        self.maxAngle = 45
        self.search_turn_speed = 0.9

        self.going_to_ball = False

        self.sizeThreshold = 190
        self.flag = True

        self.delta = 0
        self.last_time = None
        self.firstImageFlag = False
        self.not_going_to_ball = True

        self.maxTimeSinceBallSeen = 8.0
        self.timeBallSeen = 0.0

    def computeFPS(self):
        current_time = time.time()

        if self.last_time is not None:
            self.delta = 1.0 / (current_time - self.last_time)
            #rospy.loginfo(f"Current FPS: {self.delta:.2f}")

        self.last_time = current_time
        pass

    def image_callback(self, msg):
        """
        Callback function to process the received image and detect red objects.
        """
        self.computeFPS()
        try:
                if self.firstImageFlag:
                        # Process the image to detect red color
                        movement_cmd = self.process_image(msg)
                        self.buffer_movement_cmd = movement_cmd

                        # Publish movement command
                        self.publisher.publish(movement_cmd)
                else:
                        msg = Twist()
                        msg.linear.x = 0.01
                        self.publisher.publish(msg)
                        self.firstImageFlag = True

        except CvBridgeError as e:
            rospy.logerr("CvBridge Error: {}".format(e))

    def process_image(self, image):
        """
        Detect red color in the image and determine movement.
        """
        twist_msg = Twist()
        #Convert ROS Image message to OpenCV format
        cv_image = self.bridge.imgmsg_to_cv2(image, desired_encoding="bgr8")
        frame_height, frame_width, channels = cv_image.shape

        # Convert image to HSV color space
        hsv = cv2.cvtColor(cv_image, cv2.COLOR_BGR2HSV)

        # Define the red color range (OpenCV uses HSV for better color segmentation)
        lower_red1 = np.array([0, 97, 132])   # Lower boundary for red
        upper_red1 = np.array([6, 255, 255]) # Upper boundary for red
        #lower_red2 = np.array([170, 120, 70]) # Second lower boundary (red appears at both ends of HSV spectrum)
        #upper_red2 = np.array([180, 255, 255])# Second upper boundary

        # Create masks to detect red color in the image
        mask = cv2.inRange(hsv, lower_red1, upper_red1)
        #mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        #mask = mask1 + mask2  # Combine both masks

        # Find contours of detected red regions
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            self.timeBallSeen = time.time()
            self.explorer_publisher.publish(1)
            # Find the largest red object
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)

            # Get bounding box around the red object
            x, y, w, h = cv2.boundingRect(largest_contour)
            center_x = x + w // 2  # Find center of red object
            img_center_x = cv_image.shape[1] // 2  # Center of the image

            # Define movement logic based on object position
            if self.flag:
                self.flag = False
                self.sound_publisher.publish("SEARCHING")
                rospy.sleep(0.5)
                print("searching")
            if area > self.sizeThreshold:  # Ignore small objects (filter out noise)
                angle_to_ball = self.calculate_horizontal_angle(center_x, frame_width, self.maxAngle)
                self.search_turn_speed = -self.computeTurnSpeed(angle_to_ball) #adjust turn speed to follow ball
                if abs(center_x - img_center_x) < 100:
                    twist_msg.linear.x = 0 # Move forward
                    twist_msg.angular.z = 0.0
                    
                    rospy.loginfo(f"Item area = {area}")
                    rospy.loginfo("Red object detected! Skibidiing toward it.")
                    #self.going_to_ball = True

                    self.image_publisher.publish(image)
                    self.sound_publisher.publish("SKIBIDI FORWARD")
                elif center_x < img_center_x:
                    twist_msg.linear.x = 0
                    twist_msg.angular.z = 0 # Turn left
                else:
                    twist_msg.linear.x = 0
                    twist_msg.angular.z = 0  # Turn right
            else:
                twist_msg.linear.x = 0
                twist_msg.angular.z = 0 # Rotate to search
        else:
                self.sound_publisher.publish("SEARCHING")
                if time.time() - self.timeBallSeen < self.maxTimeSinceBallSeen:
                        #twist_msg.angular.z = self.search_turn_speed  # Rotate to search
                        twist_msg.angular.z = 0
                        print("i still remember...")
                else:
                        print("exploring")
        return twist_msg

    def calculate_horizontal_angle(self, x_center, frame_width, max_angle):
            """
            Calculate the angle from the center of the frame.
            Negative = left, Positive = right.
            """
            threshold = 1
            offset = x_center - (frame_width / 2)
            normalized_offset = offset / (frame_width / 2)
            angle = normalized_offset * max_angle #link to time between frames

            if abs(angle) < threshold:
                angle = 0
            return angle

    def computeTurnSpeed(self, angle):
        speed = 0
        max_speed = 100
        min_speed = 10
        speed = (angle - self.minAngle) / (self.maxAngle - self.minAngle) * (max_speed - min_speed) + min_speed
        return speed/self.delta

    def run(self):
        rospy.spin()
        

if __name__ == "__main__":
    try:
        controller = TurtlebotVisionController()
        controller.run()
    except rospy.ROSInterruptException:
        pass
