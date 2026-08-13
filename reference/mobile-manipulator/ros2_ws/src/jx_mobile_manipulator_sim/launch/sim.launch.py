from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable, DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription, RegisterEventHandler
from launch.events import Shutdown
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    description_share = FindPackageShare("jx_mobile_manipulator_description")
    sim_share = FindPackageShare("jx_mobile_manipulator_sim")
    model = PathJoinSubstitution([description_share, "urdf", "reference_mobile_manipulator.urdf.xacro"])
    robot_description = ParameterValue(Command(["xacro ", model]), value_type=str)
    gz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare("ros_gz_sim"), "launch", "gz_sim.launch.py"])),
        launch_arguments={"gz_args": ["-r -s ", PathJoinSubstitution([sim_share, "worlds", "reference_world.sdf"])], "on_exit_shutdown": "true"}.items(),
    )
    state_publisher = Node(package="robot_state_publisher", executable="robot_state_publisher", parameters=[{"robot_description": robot_description, "use_sim_time": use_sim_time}])
    spawn = Node(package="ros_gz_sim", executable="create", arguments=["-name", "reference_mobile_manipulator", "-topic", "robot_description", "-z", "0.1"], output="screen")
    bridge = Node(package="ros_gz_bridge", executable="parameter_bridge", parameters=[{"config_file": PathJoinSubstitution([sim_share, "config", "bridge.yaml"]), "use_sim_time": use_sim_time}])
    spawners = [Node(package="controller_manager", executable="spawner", arguments=[name, "--controller-manager", "/controller_manager"], parameters=[{"use_sim_time": use_sim_time}]) for name in ("joint_state_broadcaster", "arm_controller", "diff_drive_controller")]

    def after_spawn(event, _context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason="robot spawn failed; controllers were not started"))]
        return spawners

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", description_share),
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", sim_share),
        gz, state_publisher, bridge, RegisterEventHandler(OnProcessExit(target_action=spawn, on_exit=after_spawn)), spawn,
    ])
