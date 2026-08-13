import ast
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))
WORKSPACE = ROOT / "reference" / "mobile-manipulator" / "ros2_ws"
SRC = WORKSPACE / "src"
ROS_MANIFEST = ROOT / "reference" / "mobile-manipulator" / "simulation" / "ros-workspace-manifest.json"
ROS_MANIFEST_RECEIPT = "85a19bebf3cf93be94f49dd897a176516fb7706edece8a44b2a8756b4685ca8f"

PACKAGES = {
    "jx_mobile_manipulator_description": {
        "ament_cmake", "xacro", "robot_state_publisher", "joint_state_publisher", "rviz2",
    },
    "jx_mobile_manipulator_sim": {
        "ament_cmake", "jx_mobile_manipulator_description", "ros_gz_sim", "ros_gz_bridge",
        "gz_ros2_control", "controller_manager", "joint_state_broadcaster",
        "joint_trajectory_controller", "diff_drive_controller", "rviz2",
    },
    "jx_mobile_manipulator_moveit_config": {
        "ament_cmake", "jx_mobile_manipulator_description", "moveit_ros_move_group",
        "moveit_ros_visualization", "moveit_configs_utils", "moveit_simple_controller_manager",
        "moveit_planners_ompl",
    },
    "jx_mobile_manipulator_nav": {
        "ament_cmake", "jx_mobile_manipulator_description", "nav2_bringup",
        "nav2_map_server", "nav2_lifecycle_manager",
    },
    "jx_mobile_manipulator_scenarios": {
        "ament_cmake", "jx_mobile_manipulator_sim", "rosbag2", "rosbag2_storage_mcap",
    },
}

ARM_JOINTS = [f"joint_{index}" for index in range(1, 7)]
WHEEL_JOINTS = ["left_wheel_joint", "right_wheel_joint"]


def text(path):
    return path.read_text(encoding="utf-8")


def has_safe_yaml_shape(value: str) -> bool:
    """Reject malformed text without making the portable test suite need PyYAML.

    The live ROS consumer gate remains responsible for full parameter parsing.
    Here we require UTF-8, space indentation, balanced flow collections, and a
    mapping/list token on every meaningful line; semantic assertions below cover
    the owned controller and Nav2 values.
    """
    if not value.endswith("\n") or "\t" in value:
        return False
    depth = 0
    for raw in value.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line or line in {"---", "..."}:
            continue
        depth += line.count("[") + line.count("{") - line.count("]") - line.count("}")
        if depth < 0:
            return False
    return depth == 0


class ReferenceRosWorkspaceTests(unittest.TestCase):
    def test_workspace_is_hash_bound_to_model_sources_and_external_receipt(self):
        from assurance.simulation.artifacts import validate_ros_workspace_manifest

        self.assertTrue(ROS_MANIFEST.is_file())
        self.assertEqual(
            [],
            validate_ros_workspace_manifest(
                ROOT / "reference" / "mobile-manipulator", ROS_MANIFEST, ROS_MANIFEST_RECEIPT
            ),
        )

    def test_workspace_manifest_rejects_tampered_consumer_or_source(self):
        from assurance.simulation.artifacts import validate_ros_workspace_manifest

        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "reference"
            shutil.copytree(ROOT / "reference" / "mobile-manipulator", copied)
            target = copied / "ros2_ws" / "src" / "jx_mobile_manipulator_sim" / "config" / "bridge.yaml"
            target.write_text(target.read_text(encoding="utf-8") + "# tamper\n", encoding="utf-8")
            self.assertTrue(
                any("outputs SHA-256 mismatch" in error for error in validate_ros_workspace_manifest(copied, copied / "simulation" / "ros-workspace-manifest.json", ROS_MANIFEST_RECEIPT))
            )

    def test_workspace_has_exact_packages_and_build_metadata(self):
        self.assertTrue(SRC.is_dir(), "reference ROS 2 workspace is missing")
        observed = {item.name for item in SRC.iterdir() if item.is_dir()}
        self.assertEqual(set(PACKAGES), observed)
        for name, dependencies in PACKAGES.items():
            with self.subTest(package=name):
                package = SRC / name
                root = ET.parse(package / "package.xml").getroot()
                self.assertEqual("3", root.get("format"))
                self.assertEqual(name, root.findtext("name"))
                declared = {
                    node.text for tag in ("buildtool_depend", "depend", "exec_depend")
                    for node in root.findall(tag)
                }
                self.assertTrue(dependencies <= declared, dependencies - declared)
                cmake = text(package / "CMakeLists.txt")
                self.assertIn(f"project({name})", cmake)
                self.assertIn("find_package(ament_cmake REQUIRED)", cmake)
                self.assertIn("install(DIRECTORY", cmake)
                self.assertIn("ament_package()", cmake)
        for path in SRC.rglob("*.yaml"):
            with self.subTest(yaml=path.relative_to(SRC)):
                self.assertTrue(has_safe_yaml_shape(text(path)))

    def test_description_xacro_owns_frames_joints_interfaces_and_sim_only_hardware(self):
        path = SRC / "jx_mobile_manipulator_description" / "urdf" / "reference_mobile_manipulator.urdf.xacro"
        body = text(path)
        root = ET.fromstring(body)
        self.assertEqual("reference_mobile_manipulator", root.get("name"))
        self.assertIn('xacro:arg name="use_sim" default="true"', body)
        self.assertIn('<xacro:if value="$(arg use_sim)">', body)
        self.assertIn("gz_ros2_control/GazeboSimSystem", body)
        self.assertIn('filename="libgz_ros2_control-system.so"', body)
        self.assertIn('sensor name="navigation_lidar" type="gpu_lidar"', body)
        self.assertNotIn("mock_components/GenericSystem", body)
        self.assertNotRegex(body, r"/dev/|serial|ethercat|can[0-9]|SocketCAN")
        links = {node.get("name") for node in root.findall("link")}
        links.update(node.get("name") for node in root.findall("{http://www.ros.org/wiki/xacro}cylinder_link"))
        required_links = {
            "base_link", "front_caster_link", "rear_caster_link", "left_wheel_link",
            "right_wheel_link", "imu_link", "lidar_link", "tool0",
            *(f"arm_link_{index}" for index in range(1, 7)),
        }
        self.assertTrue(required_links <= links, required_links - links)
        joints = {node.get("name") for node in root.findall("joint")}
        self.assertTrue(set(ARM_JOINTS + WHEEL_JOINTS) <= joints)
        controls = {node.get("name"): node for node in root.findall(".//ros2_control/joint")}
        self.assertEqual(set(ARM_JOINTS + WHEEL_JOINTS), set(controls))
        for joint in ARM_JOINTS:
            self.assertEqual({"position"}, {node.get("name") for node in controls[joint].findall("command_interface")})
        for joint in WHEEL_JOINTS:
            self.assertEqual({"velocity"}, {node.get("name") for node in controls[joint].findall("command_interface")})
        physical = ET.parse(ROOT / "reference" / "mobile-manipulator" / "robot.urdf").getroot()
        for name in ["base_link", *[f"arm_link_{index}" for index in range(1, 7)]]:
            source = physical.find(f"link[@name='{name}']/inertial")
            self.assertIn(f'mass="{source.find("mass").get("value")}"', body)
            for field in ("ixx", "iyy", "izz"):
                self.assertIn(f'{field}="{source.find("inertia").get(field)}"', body)

    def test_sim_world_launch_and_bridge_are_harmonic_headless_safe(self):
        package = SRC / "jx_mobile_manipulator_sim"
        world = ET.parse(package / "worlds" / "reference_world.sdf").getroot()
        self.assertEqual("1.11", world.get("version"))
        owner = world.find("world")
        plugins = {(node.get("filename"), node.get("name")) for node in owner.findall("plugin")}
        for filename in (
            "gz-sim-physics-system", "gz-sim-user-commands-system",
            "gz-sim-scene-broadcaster-system", "gz-sim-sensors-system", "gz-sim-imu-system",
        ):
            self.assertTrue(any(item[0] == filename for item in plugins), filename)
        self.assertIsNotNone(owner.find("physics/max_step_size"))
        self.assertNotIn("fuel.gazebosim.org", text(package / "worlds" / "reference_world.sdf"))

        launch = text(package / "launch" / "sim.launch.py")
        for token in (
            "AppendEnvironmentVariable", "GZ_SIM_RESOURCE_PATH", "ros_gz_sim", "gz_sim.launch.py",
            "ParameterValue", "Command", "xacro ", "use_sim_time", "-z", "0.1",
            "robot_state_publisher", "ros_gz_bridge", "controller_manager", '"-r -s "',
        ):
            self.assertIn(token, launch)
        self.assertNotIn("gazebo_ros", launch)
        self.assertNotIn('"headless": headless', launch)
        self.assertIn("OnProcessExit(target_action=spawn", launch)
        self.assertNotIn("OnProcessStart(target_action=spawn", launch)
        self.assertIn("event.returncode", launch)
        self.assertIn("Shutdown(reason=", launch)
        self.assertIn('AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", description_share)', launch)
        self.assertIn('AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", sim_share)', launch)

        bridge = text(package / "config" / "bridge.yaml")
        for token in (
            "ros_topic_name: /clock", "gz_topic_name: /clock",
            "rosgraph_msgs/msg/Clock", "gz.msgs.Clock", "GZ_TO_ROS",
            "ros_topic_name: /imu/data", "sensor_msgs/msg/Imu", "gz.msgs.IMU",
            "ros_topic_name: /scan", "sensor_msgs/msg/LaserScan", "gz.msgs.LaserScan",
        ):
            self.assertIn(token, bridge)

    def test_controller_moveit_nav_and_scenario_consumers_are_explicit(self):
        src = SRC
        controllers = text(src / "jx_mobile_manipulator_sim" / "config" / "controllers.yaml")
        for joint in ARM_JOINTS + WHEEL_JOINTS:
            self.assertEqual(1, len(re.findall(rf"\b{re.escape(joint)}\b", controllers)))
        for token in (
            "joint_state_broadcaster", "joint_trajectory_controller/JointTrajectoryController",
            "diff_drive_controller/DiffDriveController", "use_stamped_vel: true",
            "left_wheel_names: [left_wheel_joint]", "right_wheel_names: [right_wheel_joint]",
        ):
            self.assertIn(token, controllers)

        moveit = src / "jx_mobile_manipulator_moveit_config"
        srdf = ET.parse(moveit / "config" / "reference_mobile_manipulator.srdf").getroot()
        chain = srdf.find("group[@name='manipulator']/chain")
        self.assertEqual(("base_link", "tool0"), (chain.get("base_link"), chain.get("tip_link")))
        moveit_controllers = text(moveit / "config" / "moveit_controllers.yaml")
        self.assertIn("action_ns: follow_joint_trajectory", moveit_controllers)
        self.assertNotIn("action_ns: arm_controller/", moveit_controllers)
        move_group = text(moveit / "launch" / "move_group.launch.py")
        self.assertIn("moveit_configs_utils", move_group)
        self.assertIn('mappings={"use_sim": "false"}', move_group)
        self.assertIn("planning_pipelines", move_group)
        ompl = text(moveit / "config" / "ompl_planning.yaml")
        # Jazzy scopes planner plugins under the selected `ompl` pipeline and
        # accepts a vector, rather than the retired scalar `planning_plugin`.
        self.assertRegex(ompl, r"planning_plugins:\s*\n\s+- ompl_interface/OMPLPlanner")
        self.assertNotIn("planning_plugin:", ompl)
        # MoveIt Jazzy declares adapter parameters as string arrays.  YAML folded
        # scalars deserialize as a single string and crash move_group at startup.
        self.assertRegex(ompl, r"request_adapters:\s*\n\s+- ")
        self.assertRegex(ompl, r"response_adapters:\s*\n\s+- ")

        nav = src / "jx_mobile_manipulator_nav"
        nav_params = text(nav / "config" / "nav2_params.yaml")
        for token in (
            "use_sim_time: true", "robot_base_frame: base_link", "global_frame: map",
            "odom_topic: /odom", "scan: {topic: /scan", "enable_stamped_cmd_vel: true",
            "footprint:", "progress_checker_plugins", "goal_checker_plugins",
            "observation_sources: [scan]", "data_type: LaserScan",
            "cmd_vel_in_topic: cmd_vel_smoothed", "cmd_vel_out_topic: /diff_drive_controller/cmd_vel",
        ):
            self.assertIn(token, nav_params)
        nav_launch = text(nav / "launch" / "navigation.launch.py")
        self.assertIn("nav2_bringup", nav_launch)
        self.assertIn("bringup_launch.py", nav_launch)
        self.assertIn('"map": map_file', nav_launch)
        self.assertIn('"use_localization": "true"', nav_launch)
        self.assertIn('"use_composition": "False"', nav_launch)
        self.assertIn("cmd_vel_out_topic: /diff_drive_controller/cmd_vel", nav_params)
        self.assertNotIn("cmd_vel_topic:", nav_params)

        scenarios = text(src / "jx_mobile_manipulator_scenarios" / "config" / "scenarios.yaml")
        for token in ("nominal_drive", "nominal_arm", "safe_stop", "max_duration_s", "rosbag2_storage_mcap"):
            self.assertIn(token, scenarios)

    def test_launch_files_compile_and_all_ros_nodes_declare_sim_time(self):
        launch_files = sorted(SRC.rglob("*.launch.py"))
        self.assertGreaterEqual(len(launch_files), 5)
        for path in launch_files:
            with self.subTest(path=path.relative_to(SRC)):
                ast.parse(text(path), filename=str(path))
                source = text(path)
                tree = ast.parse(source, filename=str(path))
                node_calls = [
                    call for call in ast.walk(tree)
                    if isinstance(call, ast.Call)
                    and ((isinstance(call.func, ast.Name) and call.func.id == "Node")
                         or (isinstance(call.func, ast.Attribute) and call.func.attr == "Node"))
                ]
                for call in node_calls:
                    parameters = next((item.value for item in call.keywords if item.arg == "parameters"), None)
                    package = next((item.value.value for item in call.keywords if item.arg == "package" and isinstance(item.value, ast.Constant)), None)
                    executable = next((item.value.value for item in call.keywords if item.arg == "executable" and isinstance(item.value, ast.Constant)), None)
                    if (package, executable) == ("ros_gz_sim", "create"):
                        self.assertIsNone(parameters, "Gazebo create is intentionally a one-shot CLI node")
                        continue
                    self.assertIsNotNone(parameters, "persistent ROS Node must declare use_sim_time")
                    segment = ast.get_source_segment(source, parameters) or ""
                    self.assertIn("use_sim_time", segment)

    def test_tf_ownership_and_command_chain_have_one_authority(self):
        controllers = text(SRC / "jx_mobile_manipulator_sim" / "config" / "controllers.yaml")
        self.assertIn("enable_odom_tf: true", controllers)
        self.assertIn("base_frame_id: base_link", controllers)
        self.assertIn("odom_frame_id: odom", controllers)
        sim_launch = text(SRC / "jx_mobile_manipulator_sim" / "launch" / "sim.launch.py")
        self.assertNotIn("static_transform_publisher", sim_launch)
        nav_params = text(SRC / "jx_mobile_manipulator_nav" / "config" / "nav2_params.yaml")
        self.assertGreaterEqual(nav_params.count("enable_stamped_cmd_vel: true"), 4)
        self.assertNotIn("geometry_msgs/msg/Twist\n", nav_params)

    def test_rviz_covers_robot_tf_and_every_simulated_sensor(self):
        configs = "\n".join(text(path) for path in SRC.rglob("*.rviz"))
        for display in ("rviz_default_plugins/RobotModel", "rviz_default_plugins/TF", "rviz_default_plugins/Odometry"):
            self.assertIn(display, configs)
        self.assertIn("/imu/data", configs)
        self.assertIn("rviz_default_plugins/LaserScan", configs)
        self.assertIn("/scan", configs)
        self.assertIn("/plan", configs)

    def test_workspace_contains_no_real_hardware_ports_or_plugins(self):
        forbidden = re.compile(r"/dev/(tty|serial|can)|ethercat|socketcan|modbus|real_hardware", re.IGNORECASE)
        for path in sorted(
            item for item in SRC.rglob("*")
            if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
        ):
            with self.subTest(path=path.relative_to(SRC)):
                self.assertIsNone(forbidden.search(text(path)))


if __name__ == "__main__":
    unittest.main()
