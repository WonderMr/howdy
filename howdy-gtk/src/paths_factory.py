from pathlib import PurePath
import paths

# Dlib model names
models = [
    "shape_predictor_5_face_landmarks.dat",
    "mmod_human_face_detector.dat",
    "dlib_face_recognition_resnet_model_v1.dat",
]


def config_file_path() -> str:
    """Return the path to the config file"""
    return str(paths.config_dir / "config.ini")


def user_models_dir_path() -> PurePath:
    """Return the path to the user models directory"""
    return paths.user_models_dir


def user_model_path(user: str) -> str:
    """Return the path to a specific user's model file"""
    return str(paths.user_models_dir / f"{user}.dat")


def logo_path() -> str:
    """Return the path to the logo file"""
    return str(paths.data_dir / "logo.png")


def onboarding_wireframe_path() -> str:
    """Return the path to the onboarding wireframe file"""
    return str(paths.data_dir / "onboarding.glade")


def main_window_wireframe_path() -> str:
    """Return the path to the main window wireframe file"""
    return str(paths.data_dir / "main.glade")


def dlib_data_dir_path() -> str:
    """Return the path to the dlib data directory"""
    return str(paths.dlib_data_dir)


def shape_predictor_5_face_landmarks_path() -> str:
    """Return the path to the shape predictor model"""
    return str(paths.dlib_data_dir / models[0])


def mmod_human_face_detector_path() -> str:
    """Return the path to the face detector model"""
    return str(paths.dlib_data_dir / models[1])


def dlib_face_recognition_resnet_model_v1_path() -> str:
    """Return the path to the face recognition model"""
    return str(paths.dlib_data_dir / models[2])
