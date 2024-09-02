import os
import numpy as np
from fastapi import FastAPI, HTTPException, Body
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.efficientnet import preprocess_input
from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.layers import Dense, Dropout, GlobalAveragePooling2D
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras import Model
from tensorflow.keras.models import load_model
import logging
import tensorflow as tf
import time
import shutil
import json


app = FastAPI()

volume_path = 'volume_data'

log_folder = os.path.join(volume_path, "logs")
os.makedirs(log_folder, exist_ok = True)
logging.basicConfig(filename=os.path.join(log_folder, "inference.log"), level=logging.INFO, 
                    format='%(asctime)s %(levelname)s %(message)s', 
                    datefmt='%d/%m/%Y %I:%M:%S %p')

mlruns_path = os.path.join(volume_path, 'mlruns')
    

class predictClass:
    def __init__(self, model_path, img_size=(224, 224)):
        self.img_size = img_size
        self.model_path = model_path
        
        # Vérifier l'existence du fichier modèle et du dossier de test
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Le fichier modèle {self.model_path} n'existe pas.")
        
        # Configurer GPU si disponible
        self.configure_gpu()
        
        try:
            self.model = load_model(os.path.join(model_path, 'saved_model.h5'))
            with open(os.path.join(model_path, 'classes.json'), 'r') as file:
                self.class_names = json.load(file)
            # self.num_classes = len(self.class_names)
            logging.info("Modèle chargé avec succès.")
        except Exception as e:
            logging.error(f"Erreur lors de l'initialisation : {str(e)}")
            raise

    def configure_gpu(self):
        gpus = tf.config.experimental.list_physical_devices('GPU')
        if gpus:
            try:
                for gpu in gpus:
                    tf.config.experimental.set_memory_growth(gpu, True)
                logging.info(f"GPU(s) configuré(s) pour une utilisation dynamique de la mémoire.")
            except RuntimeError as e:
                logging.error(f"Erreur lors de la configuration du GPU : {e}")

    def predict(self, image_path):
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"L'image {image_path} n'existe pas.")
        
        try:
            img = image.load_img(image_path, target_size=self.img_size)
            img_array = image.img_to_array(img)
            img_array_expanded_dims = np.expand_dims(img_array, axis=0)
            img_ready = preprocess_input(img_array_expanded_dims)
            
            prediction = self.model.predict(img_ready)
            
            highest_score_index = int(np.argmax(prediction))
            meilleure_classe = self.class_names[str(highest_score_index)]
            highest_score = float(np.max(prediction))
    
            
            logging.info(f"Prédiction effectuée : classe = {meilleure_classe}, score = {highest_score}")
            return meilleure_classe, highest_score
        except Exception as e:
            logging.error(f"Erreur lors de la prédiction : {str(e)}")
            raise

    # def get_class_names(self):
    #     return self.class_names
    
def load_classifier(run_id):
    model_path = os.path.join(volume_path, f'mlruns/157975935045122495/{run_id}/artifacts/model/')
    classifier = predictClass(model_path = model_path)
    classifier.predict('./load_image.jpg')
    return classifier
    
prod_model_id_path = os.path.join(mlruns_path, 'prod_model_id.txt')
while not os.path.exists(prod_model_id_path):
    time.sleep(1)

with open(prod_model_id_path, 'r') as file:
    run_id = file.read()

classifier = load_classifier(run_id)
    
@app.get("/")
def read_root():
    return {"Status": "OK"}

@app.get("/predict")
async def predict(file_name: str):
    try:
        temp_folder = os.path.join(volume_path, 'temp_images')
        image_path = os.path.join(temp_folder, file_name)
        logging.info("Début de la prédiction")
        meilleure_classe, highest_score = classifier.predict(image_path)
        logging.info(f"Prédiction terminée: {meilleure_classe}, score: {highest_score}")
        return {"prediction": meilleure_classe, "score": highest_score, "filename": file_name}
    
    except Exception as e:
        logging.error(f'Failed to open the image and/or do the inference: {e}')
        raise HTTPException(status_code=500, detail="Internal server error")
    
@app.post("/switchmodel")
async def switch_model(run_id: str = Body(...)):
    try:
        global classifier
        run_id = run_id.removeprefix('run_id=')
        with open(os.path.join(mlruns_path, 'prod_model_id.txt'), 'w') as file:
            file.write(run_id)
            
        classifier = load_classifier(run_id)
        logging.info(f"Changement de modèle effectué !")
        return {f"Le nouveau modèle utilisé provient maintenant du run id suivant : {run_id}"}
    
    except Exception as e:
        logging.error(f'Failed to open the image and/or do the inference: {e}')
        raise HTTPException(status_code=500, detail="Internal server error")